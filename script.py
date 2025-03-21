import os
import time
import json
import logging
from typing import Dict, Any, Optional

import requests
from web3 import Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware
from dotenv import load_dotenv

# --- Configuration Loading ---
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - (%(name)s) - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('BridgeEventListener')


class ChainConnector:
    """
    Manages the connection to a specific blockchain via a Web3 provider.

    This class encapsulates the logic for establishing and verifying a connection
    to an Ethereum-compatible node. It handles different types of RPC endpoints
    (HTTP, WebSocket) and includes a retry mechanism for initial connection.
    """

    def __init__(self, rpc_url: str, chain_name: str):
        """
        Initializes the connector with the RPC URL and a descriptive name for the chain.

        Args:
            rpc_url (str): The HTTP or WebSocket URL of the blockchain node.
            chain_name (str): A human-readable name for the chain (e.g., 'SourceChain-Sepolia').
        """
        self.rpc_url = rpc_url
        self.chain_name = chain_name
        self.web3: Optional[Web3] = None
        self.connect()

    def connect(self, max_retries: int = 3, delay: int = 5) -> None:
        """
        Establishes a connection to the blockchain node.

        It retries the connection in case of failure. It also injects POA middleware
        if the chain is detected to be a Proof-of-Authority network.

        Args:
            max_retries (int): Maximum number of connection attempts.
            delay (int): Seconds to wait between retries.
        """
        for attempt in range(max_retries):
            try:
                logger.info(f'Attempting to connect to {self.chain_name} at {self.rpc_url}...')
                if self.rpc_url.startswith('http'):
                    self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
                elif self.rpc_url.startswith('ws'):
                    self.web3 = Web3(Web3.WebsocketProvider(self.rpc_url))
                else:
                    raise ValueError('Invalid RPC URL scheme. Use http or ws.')

                if self.web3.is_connected():
                    # Inject middleware for PoA chains like Goerli, Sepolia, Polygon Mumbai
                    self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
                    chain_id = self.web3.eth.chain_id
                    logger.info(f'Successfully connected to {self.chain_name}. Chain ID: {chain_id}')
                    return
                else:
                    raise ConnectionError(f'Web3 connection failed for {self.chain_name}.')

            except Exception as e:
                logger.error(f'Connection attempt {attempt + 1}/{max_retries} to {self.chain_name} failed: {e}')
                if attempt < max_retries - 1:
                    time.sleep(delay)
        
        logger.critical(f'Could not establish connection to {self.chain_name} after {max_retries} attempts.')
        # In a real-world scenario, this might trigger a system alert.
        raise ConnectionError(f'Failed to connect to {self.chain_name}.')

    def get_contract(self, address: str, abi: Dict[str, Any]) -> Optional[Contract]:
        """
        Returns a Web3 contract instance if the connection is active.

        Args:
            address (str): The contract's address.
            abi (Dict[str, Any]): The contract's ABI.

        Returns:
            Optional[Contract]: A Web3 contract instance or None if not connected.
        """
        if self.web3 and self.web3.is_connected():
            return self.web3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
        logger.warning(f'Cannot get contract for {self.chain_name}; Web3 not connected.')
        return None


class StateDB:
    """
    A simple in-memory key-value store to simulate a persistent database.

    This class is used to track the state of the listener, such as the last processed
    block number and a set of processed transaction hashes to prevent replay attacks
    or double-processing of events.
    """

    def __init__(self, state_file: str = 'state.json'):
        """
        Initializes the state database, loading from a file if it exists.

        Args:
            state_file (str): The file path to persist the state.
        """
        self.state_file = state_file
        self.state: Dict[str, Any] = {
            'last_processed_block': 0,
            'processed_tx_hashes': []
        }
        self.load_state()

    def load_state(self) -> None:
        """
        Loads the state from the JSON file.
        """
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
                    logger.info(f'Loaded state from {self.state_file}: Last block {self.get_last_processed_block()}')
            else:
                logger.info('No state file found. Starting with a fresh state.')
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f'Error loading state file: {e}. Starting with a fresh state.')
            # Re-initialize state to ensure it's clean
            self.state = {'last_processed_block': 0, 'processed_tx_hashes': []}

    def save_state(self) -> None:
        """
        Persists the current state to the JSON file.
        """
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=4)
        except IOError as e:
            logger.error(f'Could not save state to {self.state_file}: {e}')

    def get_last_processed_block(self) -> int:
        return self.state['last_processed_block']

    def set_last_processed_block(self, block_number: int) -> None:
        self.state['last_processed_block'] = block_number

    def is_tx_processed(self, tx_hash: str) -> bool:
        return tx_hash in self.state['processed_tx_hashes']

    def add_processed_tx(self, tx_hash: str) -> None:
        # To prevent the list from growing indefinitely, one might implement a cleanup strategy
        if len(self.state['processed_tx_hashes']) > 10000: # Example limit
            self.state['processed_tx_hashes'].pop(0)
        self.state['processed_tx_hashes'].append(tx_hash)


class EventProcessor:
    """
    Handles the business logic for processing a detected cross-chain event.

    This is a simulation. In a real bridge, this component would be responsible for
    creating, signing, and broadcasting a transaction on the destination chain to
    mint tokens or execute a corresponding action.
    """
    def __init__(self, dest_connector: ChainConnector, dest_contract: Contract):
        self.dest_connector = dest_connector
        self.dest_contract = dest_contract
        # In a real app, load this from a secure vault or environment variable
        self.relayer_private_key = os.getenv('RELAYER_PRIVATE_KEY')
        if not self.relayer_private_key:
            logger.warning('RELAYER_PRIVATE_KEY not set. Running in simulation-only mode.')
        else:
            self.relayer_account = dest_connector.web3.eth.account.from_key(self.relayer_private_key)
            logger.info(f'Relayer account configured for destination chain: {self.relayer_account.address}')


    def process_event(self, event: Dict[str, Any]) -> bool:
        """
        Simulates processing a 'TokensLocked' event.

        Args:
            event (Dict[str, Any]): The event data from web3.py.

        Returns:
            bool: True if processing was successful (or successfully simulated), False otherwise.
        """
        tx_hash = event['transactionHash'].hex()
        log_index = event['logIndex']
        args = event['args']
        logger.info(f"Processing event from Tx {tx_hash} (Log Index: {log_index}): User {args['user']} locked {args['amount']} tokens to send to {args['destinationChainId']}.")
        
        # --- Simulation of Destination Chain Transaction ---
        if not self.relayer_private_key:
            logger.info(f"[SIMULATION] Would call 'mint' on destination contract for user {args['user']} with amount {args['amount']}.")
            return True

        # --- Real Transaction Logic (if private key is provided) ---
        try:
            dest_web3 = self.dest_connector.web3
            nonce = dest_web3.eth.get_transaction_count(self.relayer_account.address)
            
            # This is a simplified gas price fetching. A production system would use a more robust strategy.
            gas_price = self._get_dynamic_gas_price()

            # Build the transaction to call the 'mint' function on the destination contract
            tx_data = self.dest_contract.functions.mint(
                args['user'],
                args['amount'],
                event['transactionHash'] # Use source tx hash as a unique identifier to prevent replays
            ).build_transaction({
                'from': self.relayer_account.address,
                'nonce': nonce,
                'gas': 200000, # This should be estimated properly
                'gasPrice': gas_price
            })

            signed_tx = dest_web3.eth.account.sign_transaction(tx_data, self.relayer_private_key)
            
            logger.info(f"Submitting transaction to destination chain with nonce {nonce} and gas price {gas_price}.")
            sent_tx_hash = dest_web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            logger.info(f"Transaction submitted to destination chain. Tx Hash: {sent_tx_hash.hex()}")

            # Wait for transaction receipt (optional, but good for confirmation)
            receipt = dest_web3.eth.wait_for_transaction_receipt(sent_tx_hash, timeout=120)
            if receipt.status == 1:
                logger.info(f'Successfully processed event. Destination tx confirmed in block {receipt.blockNumber}.')
                return True
            else:
                logger.error(f'Destination transaction failed! Tx Hash: {sent_tx_hash.hex()}')
                return False

        except Exception as e:
            logger.error(f'Error processing event and submitting to destination chain: {e}')
            return False

    def _get_dynamic_gas_price(self) -> int:
        """
        Fetches gas price, with a fallback to an external API.
        """
        try:
            return self.dest_connector.web3.eth.gas_price
        except Exception as e:
            logger.warning(f'Could not fetch gas price from node: {e}. Falling back to external API.')
            try:
                # Example fallback using Etherscan API (replace with a generic gas station if needed)
                # This is a conceptual example; a real implementation needs an API key.
                response = requests.get('https://api.etherscan.io/api?module=proxy&action=eth_gasPrice')
                response.raise_for_status()
                gas_price_hex = response.json()['result']
                return int(gas_price_hex, 16)
            except requests.exceptions.RequestException as req_e:
                logger.error(f'External gas price API failed: {req_e}. Using a default value.')
                return Web3.to_wei(20, 'gwei') # Hardcoded fallback

class BridgeEventListener:
    """
    The main orchestrator for the cross-chain bridge event listener.

    This class ties all components together. It initializes connections, sets up
    contract listeners, and runs an infinite loop to poll for new events.
    It uses the StateDB to maintain its position and the EventProcessor to handle
    the business logic.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state_db = StateDB()
        
        # Setup source chain
        self.source_connector = ChainConnector(config['source_chain']['rpc_url'], 'SourceChain')
        source_contract_abi = self._load_abi(config['source_chain']['contract_abi_path'])
        self.source_contract = self.source_connector.get_contract(config['source_chain']['contract_address'], source_contract_abi)

        # Setup destination chain
        self.dest_connector = ChainConnector(config['destination_chain']['rpc_url'], 'DestinationChain')
        dest_contract_abi = self._load_abi(config['destination_chain']['contract_abi_path'])
        self.dest_contract = self.dest_connector.get_contract(config['destination_chain']['contract_address'], dest_contract_abi)

        if not self.source_contract or not self.dest_contract:
            raise RuntimeError('Failed to initialize one or more contracts. Check connections and configuration.')

        self.event_processor = EventProcessor(self.dest_connector, self.dest_contract)
        self.poll_interval = config.get('poll_interval', 10) # seconds
        self.block_confirmations = config.get('block_confirmations', 6)

    def _load_abi(self, path: str) -> Dict[str, Any]:
        """
        Helper function to load a contract ABI from a JSON file.
        """
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.critical(f'Failed to load ABI from {path}: {e}')
            raise

    def run(self) -> None:
        """
        Starts the main event listening loop.
        """
        logger.info('Starting cross-chain event listener...')
        while True:
            try:
                self.poll_for_events()
            except ConnectionError as e:
                logger.error(f'Connection lost: {e}. Attempting to reconnect...')
                # Attempt to re-establish connections
                try:
                    self.source_connector.connect()
                    self.dest_connector.connect()
                    logger.info('Successfully reconnected to chains.')
                except ConnectionError:
                    logger.error('Failed to reconnect. Waiting before next retry...')
                    time.sleep(60) # Wait a minute before trying the whole loop again
            except Exception as e:
                logger.error(f'An unexpected error occurred in the main loop: {e}', exc_info=True)
            
            logger.debug(f'Sleeping for {self.poll_interval} seconds...')
            time.sleep(self.poll_interval)

    def poll_for_events(self) -> None:
        """
        Polls the source chain for new 'TokensLocked' events.
        It processes blocks in chunks to avoid overwhelming the RPC node.
        """
        web3_source = self.source_connector.web3
        if not web3_source or not web3_source.is_connected():
            raise ConnectionError('Source chain is not connected.')

        # Determine the block range to scan
        latest_block = web3_source.eth.block_number
        from_block = self.state_db.get_last_processed_block() + 1
        # Process up to a block that has enough confirmations
        to_block = latest_block - self.block_confirmations

        if from_block > to_block:
            logger.info(f'No new blocks to process. Current head: {latest_block}, waiting for confirmations.')
            return
        
        # To avoid requesting a huge range, process in chunks
        chunk_size = 1000
        end_of_chunk = min(from_block + chunk_size - 1, to_block)

        logger.info(f'Scanning for events from block {from_block} to {end_of_chunk} (Latest block: {latest_block})')

        event_filter = self.source_contract.events.TokensLocked.create_filter(
            fromBlock=from_block,
            toBlock=end_of_chunk
        )

        try:
            events = event_filter.get_all_entries()
        except Exception as e:
            logger.error(f'Error fetching events from node: {e}')
            return

        if not events:
            logger.info(f'No events found in blocks {from_block}-{end_of_chunk}.')
        else:
            logger.info(f'Found {len(events)} events in blocks {from_block}-{end_of_chunk}.')
            for event in sorted(events, key=lambda e: (e['blockNumber'], e['logIndex'])):
                tx_hash = event['transactionHash'].hex()
                log_index = event['logIndex']
                unique_event_id = f'{tx_hash}-{log_index}'

                if self.state_db.is_tx_processed(unique_event_id):
                    logger.warning(f'Event {unique_event_id} has already been processed. Skipping.')
                    continue

                success = self.event_processor.process_event(event)
                if success:
                    self.state_db.add_processed_tx(unique_event_id)
                else:
                    logger.error(f'Failed to process event {unique_event_id}. It will be retried on the next run.')
                    # If processing fails, we stop at the current block to ensure we retry
                    # In a production system, you'd want a more sophisticated retry/dead-letter queue mechanism
                    self.state_db.set_last_processed_block(event['blockNumber'] - 1)
                    self.state_db.save_state()
                    return # Exit the function to force a retry from this block next time

        # If all events in the chunk are processed successfully, update the state
        self.state_db.set_last_processed_block(end_of_chunk)
        self.state_db.save_state()


if __name__ == '__main__':
    # --- Main Execution ---
    # This script requires two sample ABI JSON files: `source_abi.json` and `dest_abi.json`.
    # And a .env file with environment variables.

    # Example ABI for TokensLocked event on source chain
    SOURCE_ABI_EXAMPLE = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
                {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
                {"indexed": False, "internalType": "uint256", "name": "destinationChainId", "type": "uint256"}
            ],
            "name": "TokensLocked",
            "type": "event"
        }
    ]
    # Example ABI for mint function on destination chain
    DEST_ABI_EXAMPLE = [
        {
            "inputs": [
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "amount", "type": "uint256"},
                {"internalType": "bytes32", "name": "sourceTxHash", "type": "bytes32"}
            ],
            "name": "mint",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]

    # Create dummy ABI files if they don't exist for demonstration
    if not os.path.exists('source_abi.json'):
        with open('source_abi.json', 'w') as f: json.dump(SOURCE_ABI_EXAMPLE, f)
    if not os.path.exists('dest_abi.json'):
        with open('dest_abi.json', 'w') as f: json.dump(DEST_ABI_EXAMPLE, f)

    # Configuration is loaded from environment variables for security and flexibility.
    # A .env file should be created in the root directory.
    # Example .env:
    # SOURCE_RPC_URL="https://rpc.sepolia.org"
    # SOURCE_CONTRACT_ADDRESS="0x..."
    # DESTINATION_RPC_URL="https://rpc-mumbai.maticvigil.com"
    # DESTINATION_CONTRACT_ADDRESS="0x..."
    # RELAYER_PRIVATE_KEY="0x..."
    
    try:
        config = {
            'source_chain': {
                'rpc_url': os.getenv('SOURCE_RPC_URL'),
                'contract_address': os.getenv('SOURCE_CONTRACT_ADDRESS'),
                'contract_abi_path': 'source_abi.json'
            },
            'destination_chain': {
                'rpc_url': os.getenv('DESTINATION_RPC_URL'),
                'contract_address': os.getenv('DESTINATION_CONTRACT_ADDRESS'),
                'contract_abi_path': 'dest_abi.json'
            },
            'poll_interval': 15, # seconds
            'block_confirmations': 12 # How many blocks to wait for finality
        }

        # Basic validation
        if not all([config['source_chain']['rpc_url'], config['source_chain']['contract_address'], 
                    config['destination_chain']['rpc_url'], config['destination_chain']['contract_address']]):
            raise ValueError('One or more required environment variables are not set. Please check your .env file.')

        listener = BridgeEventListener(config)
        listener.run()
    except (ValueError, RuntimeError, ConnectionError) as e:
        logger.critical(f'Failed to initialize and run the listener: {e}')
    except KeyboardInterrupt:
        logger.info('Shutting down listener...')
