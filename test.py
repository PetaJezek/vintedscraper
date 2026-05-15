import torch
print(f"PyTorch Version: {torch.__version__}")
print(f"CUDA Version: {torch.version.cuda}")
print(f"Is CUDA available? {torch.cuda.is_available()}")

# This should now work!
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device selected: {device}")