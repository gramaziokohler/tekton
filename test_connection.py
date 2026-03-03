import sys
import os

# Ensure we can find the package
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "src")
if os.path.exists(src_dir):
    sys.path.insert(0, src_dir)

import grpc
from dlubal.api.rfem.application import Application, pack_object
from dlubal.api.rfem.application_pb2_grpc import ApplicationStub
from dlubal.api.rfem.structure_core.node_pb2 import Node

def run_test():
    print("--- DLUBAL PORT 8081 TEST ---")
    
    # 1. Try high-level Application
    try:
        app = Application(port='8081')
        print(f"SUCCESS: Application object created on Port 8081. Version: {app.get_model_list()}")
    except Exception as e:
        print(f"FAILED: Application object failed: {e}")
        app = None

    # 2. Try raw gRPC Stub
    print("\n--- RAW STUB TEST (Port 9000) ---")
    channel = grpc.insecure_channel('127.0.0.1:9000')
    stub = ApplicationStub(channel)
    
    # Test Node creation
    test_node = Node(no=999, coordinate_1=1.0, coordinate_2=2.0, coordinate_3=3.0)
    packed = pack_object(test_node)
    
    # We must provide the API key as metadata
    api_key = "PASTE_YOUR_API_KEY_HERE" # User should replace this or use the one from Grasshopper
    metadata = (('x-api-key', api_key),)
    
    success = False
    for method in ['create_object_impl', 'set_object', 'create_object']:
        if hasattr(stub, method):
            print(f"Found method: {method}. Attempting call with metadata...")
            try:
                getattr(stub, method)(packed, metadata=metadata)
                print(f"SUCCESS: Called {method} via stub!")
                success = True
                break
            except Exception as e:
                print(f"FAILED: {method} call failed: {e}")
                if "ALREADY_EXISTS" in str(e):
                    print("This is actually a SUCCESS indicator (node already exists).")
                    success = True
                    break
    
    if not success:
        print("FAILED: Could not find working creation method on stub.")
        print("Available methods on stub:")
        print([m for m in dir(stub) if not m.startswith('_')])

if __name__ == "__main__":
    run_test()
