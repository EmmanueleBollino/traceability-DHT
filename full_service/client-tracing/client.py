from solcx import compile_files, install_solc
from web3 import Web3
from eth_account import Account
from hypercube_requests import HypercubeRequests
from enum import IntEnum
from PIL import Image
import ipfshttpclient


class Brand(IntEnum):
    FERRARI = 0
    LAMBORGHINI = 1
    # MASERATI = 2


class Colour(IntEnum):
    RED = 0
    YELLOW = 1
    BLUE = 2
    # BLACK = 3
    # WHITE = 4


class Client:

    def __init__(self, blockchain_addr="http://localhost:8545", chain_id="1337", ipfs_addr="/ip4/127.0.0.1/tcp/5001", hypercube_addr="http://localhost:8880", private_key=None):
        self.blockchain_addr = blockchain_addr
        self.chain_id = chain_id
        self.ipfs_addr = ipfs_addr
        self.hypercube_addr = hypercube_addr
        self.private_key = private_key

        self.hypercube_requests = HypercubeRequests(hypercube_addr)

        self.ipfs = ipfshttpclient.connect(ipfs_addr)
        self.w3 = Web3(Web3.HTTPProvider(blockchain_addr))

        if private_key is None:
            self.acct = self.w3.eth.accounts[0]
        else:
            self.acct = Account.from_key(private_key).address
        self.w3.eth.default_account = self.acct
        print("Using account", self.acct)

        print("Initializing Factory")
        install_solc('0.8.19')

        facotry_abi, factory_bytecode = self.compile_contract(
            "./contracts/CarFactory.sol")
        self.contract = self.deploy_contract(facotry_abi, factory_bytecode)

        self.car_abi, _ = self.compile_contract("./contracts/Car.sol")

    def compile_contract(self, sol_path):
        compiled_sol = compile_files([sol_path], output_values=['abi', 'bin'])
        contract_id, contract_interface = compiled_sol.popitem()

        abi = contract_interface['abi']
        bytecode = contract_interface['bin']

        return abi, bytecode

    def deploy_contract(self, abi, bytecode, args={}):
        contract_bin = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = contract_bin.constructor(**args).transact({'from': self.acct})
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        self.contract = self.w3.eth.contract(
            address=tx_receipt.contractAddress,
            abi=abi,
            bytecode=bytecode
        )

        print(f"Contract deployed to {tx_receipt.contractAddress}")

        return self.contract

    def create_keyword(self, brand, colour):
        return brand + colour + (max(Brand) - 1) * brand
    
    def create_keyword_onehot(self, brand, colour):
        b = (2 ** brand) if brand is not None else 0
        c = (2 ** (max(Brand) + colour + 1)) if colour is not None else 0
        
        return b + c
    
    def create_car(self, brand, colour, img_path=None):
        # Add car image on IPFS
        if img_path is not None:
            ipfs_img_addr = self.ipfs.add(img_path)['Hash']
            print("IPFS image address:", ipfs_img_addr)
        else:
            ipfs_img_addr = ""
            print("No IPFS image uploaded")

        # Create new car through the car factory
        tx = self.contract.functions.createCar(brand, colour, ipfs_img_addr).transact({"from": self.acct})
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx)
        # retrieve retun value through log of emitted events by the transaction
        car_address = self.contract.events.CarCreated().process_receipt(tx_receipt)[0]['args']['_car']
        print("Created new car at", car_address)

        # Add car on hypercube
        keyword = self.create_keyword_onehot(brand, colour)
        print("Keyword", keyword)

        res = self.hypercube_requests.add_obj(car_address, keyword)
        print("Add car on hypercube:", res.text)

        return res

    def search_car(self, brand, colour):
        keyword = self.create_keyword_onehot(brand, colour)

        res = self.hypercube_requests.pin_search(keyword)
        print("Objects with keyword {}:\n".format(keyword), res.text)

        return res

    def car_info(self, address):
        contract = self.w3.eth.contract(address=address, abi=self.car_abi)

        brand = Brand(contract.functions.brand().call())
        colour = Colour(contract.functions.colour().call())
        owner = contract.functions.owner().call()
        ipfs_img = contract.functions.ipfs_img().call()

        print(brand.name, colour.name, owner, ipfs_img)

        self.ipfs.get(ipfs_img, target='/client_data/downloads')

        return brand, colour, owner, ipfs_img

    def remove_car(self, address, brand, colour):
        keyword = self.create_keyword_onehot(brand, colour)

        res = self.hypercube_requests.remove_obj(address, keyword)
        print(res)

        return res
    
    def superset_search(self, brand=None, colour=None, threshold=10):
        assert(brand is None or colour is None)
        assert(brand is not None or colour is not None)

        keyword = self.create_keyword_onehot(brand, colour)

        res = self.hypercube_requests.superset_search(keyword, threshold)
        print(res)
        print(res.text)

        return res



    # TODO (optional) attach to an already deployed factory
