import torch

# Check if CUDA is available
print(f"CUDA available: {torch.cuda.is_available()}")

# Check CUDA version
if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"Number of CUDA devices: {torch.cuda.device_count()}")
    print(f"Current CUDA device: {torch.cuda.current_device()}")
    print(f"CUDA device name: {torch.cuda.get_device_name(0)}")

# Try a simple tensor operation on GPU
if torch.cuda.is_available():
    x = torch.rand(5, 3).cuda()
    print(f"Tensor on GPU: {x}")
    print(f"Device of tensor: {x.device}")
