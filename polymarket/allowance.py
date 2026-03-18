"""
Manejo de allowances para Polymarket.
Antes de poder tradear, hay que aprobar los contratos para mover USDC.
"""
import os
import logging
from typing import Dict
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("botardo")

# Polymarket contracts on Polygon
USDC_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# ERC20 ABI for approve
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

# Conditional Token Framework ABI for setApprovalForAll
CTF_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]


class AllowanceManager:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
        self.private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
        self.wallet = os.getenv("POLYMARKET_WALLET_ADDRESS", "")

    def check_usdc_allowance(self, spender: str) -> int:
        """Check current USDC allowance for a spender"""
        usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI
        )
        return usdc.functions.allowance(
            Web3.to_checksum_address(self.wallet),
            Web3.to_checksum_address(spender),
        ).call()

    def approve_usdc(self, spender: str, amount: int = 2**256 - 1) -> str:
        """Approve USDC spending for a contract (max approval by default)"""
        usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI
        )

        tx = usdc.functions.approve(
            Web3.to_checksum_address(spender), amount
        ).build_transaction(
            {
                "from": Web3.to_checksum_address(self.wallet),
                "nonce": self.w3.eth.get_transaction_count(
                    Web3.to_checksum_address(self.wallet)
                ),
                "gas": 100000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info(f"USDC approved for {spender}: tx={tx_hash.hex()}")
        return tx_hash.hex()

    def setup_all_allowances(self) -> Dict:
        """Setup all necessary allowances for Polymarket trading"""
        results = {}

        # 1. Approve USDC for CTF Exchange
        allowance = self.check_usdc_allowance(CTF_EXCHANGE)
        if allowance < 10**6 * 100:  # Less than 100 USDC approved
            logger.info("Approving USDC for CTF Exchange...")
            results["ctf_exchange_usdc"] = self.approve_usdc(CTF_EXCHANGE)
        else:
            results["ctf_exchange_usdc"] = "already_approved"

        # 2. Approve USDC for Neg Risk CTF Exchange
        allowance2 = self.check_usdc_allowance(NEG_RISK_CTF_EXCHANGE)
        if allowance2 < 10**6 * 100:
            logger.info("Approving USDC for Neg Risk CTF Exchange...")
            results["neg_risk_usdc"] = self.approve_usdc(NEG_RISK_CTF_EXCHANGE)
        else:
            results["neg_risk_usdc"] = "already_approved"

        return results
