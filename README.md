# hypestorj

A Cross-Chain Bridge Event Listener Simulation

This repository contains a Python-based simulation of a crucial component in a decentralized cross-chain bridge: the event listener. This component, often run by entities known as relayers or oracles, is responsible for monitoring events on a source blockchain and triggering corresponding actions on a destination blockchain.

This script is designed as an architectural showcase, demonstrating a robust, modular, and resilient structure suitable for a production environment.

---

### Concept

In a typical asset bridge, a user `locks` tokens in a smart contract on a source chain (e.g., Ethereum). The bridge infrastructure must detect this `TokensLocked` event. An off-chain listener (this script) picks up the event, verifies it, and then initiates a transaction on the destination chain (e.g., Polygon) to `mint` an equivalent amount of wrapped tokens for the same user.

This script simulates this exact process:

1.  **Listens** for a specific event (`TokensLocked`) on a source chain contract.
2.  **Parses** the event data (who locked tokens, how many, etc.).
3.  **Prevents** double-processing of the same event.
4.  **Processes** the event by simulating (or actually creating, if a private key is provided) a `mint` transaction on a destination chain contract.

It is designed to be resilient against RPC node failures and maintains its state to resume from where it left off after a restart.

### Code Architecture

The script follows an object-oriented design to separate concerns, making it modular and testable. The key components are:

*   `ChainConnector`: A dedicated class to manage the Web3 connection to a specific blockchain. It handles connection logic, retries, and provides contract instances. This allows the main application to easily manage connections to multiple chains (source and destination).

*   `StateDB`: A simple, file-based state manager that simulates a local database (like SQLite or LevelDB). It keeps track of the last block number processed and the transaction hashes of events that have already been handled. This is critical for ensuring that the listener can be stopped and restarted without missing or re-processing events.

*   `EventProcessor`: This class contains the core business logic. When the listener detects a new event, it hands it off to the `EventProcessor`. This component is responsible for constructing, signing, and sending the transaction to the destination chain. For simulation purposes, it logs the action, but it can perform real transactions if configured with a private key.

*   `BridgeEventListener`: The main orchestrator class. It initializes all other components, manages the primary polling loop, coordinates the reading of events, and handles high-level error handling and reconnection logic.

### How it Works

The script executes the following flow in a continuous loop:

1.  **Initialization**: On startup, the script loads configuration from environment variables (`.env` file), including RPC URLs and contract addresses.
2.  **Connection**: It establishes connections to both the source and destination chains using the `ChainConnector`.
3.  **State Loading**: The `StateDB` loads the last processed block number from `state.json`. If the file doesn't exist, it starts from block 0.
4.  **Polling Loop**: The main loop begins.
    *   It determines the range of blocks to scan, from the `last_processed_block + 1` up to the latest block on the chain, minus a safety margin for block confirmations (`block_confirmations`).
    *   To avoid overwhelming the RPC node, it processes blocks in manageable chunks (e.g., 1000 at a time).
    *   It queries the source chain for `TokensLocked` events within that block range.
5.  **Event Handling**: For each event found:
    *   It generates a unique ID for the event (from its transaction hash and log index).
    *   It checks the `StateDB` to see if this event has already been processed. If so, it's skipped.
    *   If the event is new, it's passed to the `EventProcessor`.
6.  **Transaction Submission**: The `EventProcessor` simulates (or executes) the corresponding `mint` transaction on the destination chain.
7.  **State Update**: If the event was processed successfully, its unique ID is added to the `StateDB`, and the `last_processed_block` is updated. The state is then saved to `state.json`.
8.  **Error Handling**: If an RPC connection fails, the script will attempt to reconnect. If event processing fails, it will halt progress for that block range, ensuring the failed event is retried in the next loop iteration.
9.  **Sleep**: The script waits for a configured interval (`poll_interval`) before starting the next polling cycle.

### Usage Example

**1. Prerequisites**

*   Python 3.8+
*   Access to RPC URLs for two EVM-compatible chains (e.g., from Infura, Alchemy, or a local node). You can use testnets like Sepolia and Polygon Mumbai.
*   Deployed smart contracts on both chains that match the ABIs.

**2. Setup**

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/your-username/hypestorj.git
cd hypestorj
pip install -r requirements.txt
```

**3. Configuration**

Create a `.env` file in the root of the project directory. This file will store your sensitive configuration.

```ini
# .env file

# Source Chain (e.g., Ethereum Sepolia)
SOURCE_RPC_URL="https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"
SOURCE_CONTRACT_ADDRESS="0xYourSourceBridgeContractAddress"

# Destination Chain (e.g., Polygon Mumbai)
DESTINATION_RPC_URL="https://polygon-mumbai.infura.io/v3/YOUR_INFURA_PROJECT_ID"
DESTINATION_CONTRACT_ADDRESS="0xYourDestinationBridgeContractAddress"

# (Optional) Private key for the relayer account to send transactions on the destination chain
# If not provided, the script runs in simulation-only mode.
# IMPORTANT: Use a dedicated, firewalled account with minimal funds. DO NOT use a personal private key.
RELAYER_PRIVATE_KEY="0xabcdef123456..."
```

The script will automatically generate `source_abi.json` and `dest_abi.json` with example ABIs if they are not present.

**4. Running the Listener**

Execute the script from your terminal:

```bash
python script.py
```

**5. Expected Output**

You will see log messages indicating the script's activity.

```
2023-10-27 15:30:00 - [INFO] - (BridgeEventListener) - Starting cross-chain event listener...
2023-10-27 15:30:01 - [INFO] - (ChainConnector) - Successfully connected to SourceChain. Chain ID: 11155111
2023-10-27 15:30:02 - [INFO] - (ChainConnector) - Successfully connected to DestinationChain. Chain ID: 80001
2023-10-27 15:30:02 - [INFO] - (BridgeEventListener) - Scanning for events from block 4500001 to 4500988 (Latest block: 4501000)
2023-10-27 15:30:05 - [INFO] - (BridgeEventListener) - Found 1 events in blocks 4500001-4500988.
2023-10-27 15:30:05 - [INFO] - (EventProcessor) - Processing event from Tx 0x... (Log Index: 5): User 0x... locked 100000000 tokens to send to 80001.
2023-10-27 15:30:05 - [INFO] - (EventProcessor) - [SIMULATION] Would call 'mint' on destination contract for user 0x... with amount 100000000.
2023-10-27 15:30:17 - [INFO] - (BridgeEventListener) - Scanning for events from block 4500989 to 4500988 (Latest block: 4501001)
2023-10-27 15:30:17 - [INFO] - (BridgeEventListener) - No new blocks to process. Current head: 4501001, waiting for confirmations.
```
