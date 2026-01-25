import torch
import requests
import hashlib
import queue
import os
import threading
import time
from safetensors.torch import _tobytes 
import numpy as np
from PIL import Image
from diffusers.image_processor import VaeImageProcessor


def merge_manifest_user_changes(manifest_path, existing_data):
    """
    Reload manifest and merge user changes (favorites, rejected, notes) to preserve them.
    This prevents losing user modifications when the manifest is saved during generation.
    
    Args:
        manifest_path: Path to the manifest.json file
        existing_data: The current manifest data dictionary to update
    """
    import json
    try:
        with open(manifest_path, "r") as f:
            current_manifest = json.load(f)
        
        # Create lookup dict of current items by ID
        current_items_dict = {
            item.get("id"): item 
            for item in current_manifest.get("items", []) 
            if "id" in item
        }
        
        # Update existing_data items with any user modifications
        for item in existing_data["items"]:
            item_id = item.get("id")
            if item_id in current_items_dict:
                current_item = current_items_dict[item_id]
                # Preserve user-modified fields
                if "favorite" in current_item:
                    item["favorite"] = current_item["favorite"]
                if "rejected" in current_item:
                    item["rejected"] = current_item["rejected"]
                if "notes" in current_item:
                    item["notes"] = current_item["notes"]
                    
    except FileNotFoundError:
        # First save, no existing manifest to merge
        pass
    except Exception as e:
        print(f"[GridTester] ⚠️ Warning: Could not merge manifest changes: {e}")


# HF Remote VAE endpoints
HF_ENDPOINTS = {
    "SD": "https://q1bj3bpq6kzilnsu.us-east-1.aws.endpoints.huggingface.cloud/",
    "SDXL": "https://x2dmsqunjd6k9prw.us-east-1.aws.endpoints.huggingface.cloud/",
    "Flux": "https://whhx50ex1aryqvw6.us-east-1.aws.endpoints.huggingface.cloud/",
    "HunyuanVideo": "https://o7ywnmrahorts457.us-east-1.aws.endpoints.huggingface.cloud/"
}


def detect_model_type(model, latent_channels):
    """
    Auto-detect model type for HF Remote VAE endpoint selection
    """
    #print(f"[GridTester] 🔍 Detecting model type... latent_channels={latent_channels}")
    
    if latent_channels == 16:
        # Could be Flux, SD3, or HunyuanVideo
        if hasattr(model, 'model'):
            model_str = str(type(model.model)).lower()
            if 'xl' in model_str:
                return "SDXL"
        if hasattr(model, 'model') and hasattr(model.model, 'model_type'):
            model_type = str(model.model.model_type).lower()
            #print(f"[GridTester] 🔍 Model type attribute: {model_type}")
            if 'flux' in model_type:
                return "Flux"
            elif 'hunyuan' in model_type or 'video' in model_type:
                return "HunyuanVideo"
        
        # Check model name/path
        if hasattr(model, 'model') and hasattr(model.model, 'model_config'):
            config = str(model.model.model_config).lower()
            if 'flux' in config:
                return "Flux"
        
        # Default to Flux for 16-channel
        #print(f"[GridTester] 🔍 Defaulting to Flux for 16 channels")
        return "Flux"
    
    elif latent_channels == 4:
        # SD or SDXL - check resolution or model size
        # 1. Check model name FIRST (lightweight) ✅
        if hasattr(model, 'model'):
            model_str = str(type(model.model)).lower()
            if 'xl' in model_str or 'sdxl' in model_str:
                return "SDXL"
        
        # 2. Check model config (lightweight) ✅
        if hasattr(model, 'model') and hasattr(model.model, 'model_config'):
            config_str = str(model.model.model_config).lower()
            if 'sdxl' in config_str:
                return "SDXL"
        
        # 3. ONLY count parameters as LAST RESORT ✅
        with torch.no_grad():
            try:
                param_count = sum(p.numel() for p in model.model.diffusion_model.parameters())
                #print(f"[GridTester] 🔍 Model parameter count: {param_count:,}")
                
                if param_count > 1_000_000_000:  # > 1B params suggests SDXL
                    #print(f"[GridTester] 🔍 Detected SDXL (>1B params)")
                    return "SDXL"
                else:
                    #print(f"[GridTester] 🔍 Detected SD1.5 (<1B params)")
                    return "SD"
            except:
                pass
        
        # Fallback: check if model name contains 'xl'
        if hasattr(model, 'model'):
            model_str = str(type(model.model)).lower()
            if 'xl' in model_str or 'sdxl' in model_str:
                #print(f"[GridTester] 🔍 Detected SDXL from model name")
                return "SDXL"
        
        #print(f"[GridTester] 🔍 Defaulting to SD for 4 channels")
        return "SD"
    
    else:
        #print(f"[GridTester] ⚠️ Unknown latent channels: {latent_channels}, defaulting to SD")
        return "SD"


def remote_decode_hf(endpoint, tensor, height, width):
    """
    Send latent to HuggingFace Remote VAE endpoint for decoding
    (Simpler version using requests params)
    """
    try:
        import requests
        
        # Ensure tensor is on CPU and contiguous
        tensor = tensor.cpu().contiguous()
        
        #print(f"[GridTester] 🌐 Remote decode:")
        #print(f"  Tensor shape: {tensor.shape}")
        #print(f"  Tensor dtype: {tensor.dtype}")
        #print(f"  Height: {height}, Width: {width}")
        
        headers = {
            "Content-Type": "tensor/binary",
            "Accept": "tensor/binary"
        }
        
        # Build parameters - requests will handle repeated 'shape' params
        # by passing shape as a list in params dict
        params = {
            "do_scaling": False,
            "output_type": "pt",
            "partial_postprocess": False,
            "shape": [int(dim) for dim in tensor.shape],  # List creates repeated params!
            "dtype": str(tensor.dtype).split(".")[-1],
            "height": int(height),
            "width": int(width)
        }
        
        #print(f"[GridTester] 🌐 Parameters: {params}")
        
        # Convert tensor to bytes
        tensor_data = _tobytes(tensor, "tensor")
        #print(f"[GridTester] 🌐 Tensor bytes size: {len(tensor_data)}")
        
        # requests automatically converts list params to repeated query params!
        # shape=[1,2,3] becomes ?shape=1&shape=2&shape=3
        response = requests.post(
            endpoint,
            params=params,  # ← requests handles the shape list properly
            data=tensor_data, 
            headers=headers,
            timeout=60
        )
        
        if not response.ok:
            error_text = response.text
            #print(f"[GridTester] ❌ Remote VAE error: {error_text}")
            #print(f"[GridTester] 🌐 Request URL was: {response.request.url}")
            raise RuntimeError(f"Remote VAE decode failed: {error_text}")
        
        # Parse response
        output_tensor = response.content
        response_headers = response.headers
        
        #print(f"[GridTester] 🌐 Response headers: {dict(response_headers)}")
        
        # The response should have shape and dtype in headers
        # But format might vary - let's handle both cases
        shape_header = response_headers.get("shape", "")
        
        if shape_header:
            try:
                # Try JSON parsing first
                import json
                shape = json.loads(shape_header)
            except:
                # Fallback: parse comma-separated values
                shape = [int(x.strip()) for x in shape_header.split(",")]
        else:
            raise RuntimeError("No shape header in response")
        
        dtype_str = response_headers.get("dtype", "float32")
        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        dtype = dtype_map.get(dtype_str, torch.float32)
        
        # Map to numpy dtype for frombuffer
        numpy_dtype_map = {
            "float32": np.float32,
            "float16": np.float16,
            "bfloat16": np.float32,  # NumPy doesn't support bfloat16
        }
        numpy_dtype = numpy_dtype_map.get(dtype_str, np.float32)
        
        #print(f"[GridTester] 🌐 Parsed shape: {shape}, dtype: {dtype}, numpy_dtype: {numpy_dtype}")
        
        # Convert bytes back to tensor using correct dtype
        tensor_np = np.frombuffer(output_tensor, dtype=numpy_dtype)
        result = torch.from_numpy(tensor_np).reshape(shape).to(dtype)
        
        #print(f"[GridTester] 🌐 Result tensor shape: {result.shape}")
        
        return result
        
    except Exception as e:
        #print(f"[GridTester] ❌ Remote decode error: {e}")
        import traceback
        traceback.print_exc()
        raise


class RemoteVAEDecodeWorker:
    """
    Background worker thread for async remote VAE decoding
    """
    def __init__(self, endpoint, img_dir, manifest_path, existing_data, session_name, unique_id):
        self.endpoint = endpoint
        self.img_dir = img_dir
        self.manifest_path = manifest_path
        self.existing_data = existing_data
        self.session_name = session_name
        self.unique_id = unique_id
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self.total_decoded = 0
    
    def _worker(self):
        """Worker thread that processes decode requests"""
        while True:
            item = self.queue.get()
            
            if item is None:  # Poison pill to stop thread
                self.queue.task_done()
                break
            
            try:
                latent_tensor, meta, height, width = item
                
                #print(f"[GridTester] 🌐 Processing remote decode for image #{meta['id']}")
                #print(f"[GridTester] 🌐 Input latent shape: {latent_tensor.shape}")
                
                # Ensure batch dimension exists
                if latent_tensor.ndim == 3:
                    latent_tensor = latent_tensor.unsqueeze(0)
                    #print(f"[GridTester] 🌐 Added batch dim: {latent_tensor.shape}")
                
                # Remote decode - returns [B, C, H, W] tensor
                decoded = remote_decode_hf(self.endpoint, latent_tensor, height, width)
                
                #print(f"[GridTester] 🌐 Decoded shape: {decoded.shape}")
                #print(f"[GridTester] 🌐 Decoded dtype: {decoded.dtype}")
                
                # Use VaeImageProcessor to properly postprocess the VAE output
                # This handles denormalization from [-1, 1] to [0, 1] and format conversion
                image_processor = VaeImageProcessor(vae_scale_factor=8)
                image_processor.config.do_resize = False
                
                # Get the result and check what format it's in
                result = image_processor.postprocess(decoded, output_type="pt")
                #print(f"[GridTester] 🔧 Postprocessed shape: {result.shape}")
                #print(f"[GridTester] 🔧 Postprocessed dtype: {result.dtype}")
                
                # The postprocess with output_type="pt" returns [B, C, H, W] in [0, 1]
                # We need to convert to [H, W, C] for PIL
                image = result[0]  # Remove batch: [C, H, W]
                image = image.permute(1, 2, 0)  # Convert to [H, W, C]
                image = image.cpu().numpy()
                image_np = (image * 255).round().astype(np.uint8)
                
                #print(f"[GridTester] 🔧 Final image shape: {image_np.shape}, dtype: {image_np.dtype}")
                
                # Create PIL Image
                img = Image.fromarray(image_np)
                
                # Save image
                filename = f"img_{meta['id']}.webp"
                img.save(os.path.join(self.img_dir, filename), quality=80)
                
                meta.update({
                    "file": f"/view?filename={filename}&type=output&subfolder=benchmarks/{self.session_name}/images",
                    "rejected": False
                })
                
                # Update manifest
                import json
                self.existing_data["items"].insert(0, meta)
                
                # CRITICAL: Merge user changes before saving to preserve favorites/rejections
                merge_manifest_user_changes(self.manifest_path, self.existing_data)
                
                with open(self.manifest_path, "w") as f:
                    json.dump(self.existing_data, f, indent=4)
                
                # Send update to dashboard
                try:
                    from server import PromptServer
                    if PromptServer:
                        PromptServer.instance.send_sync("ultimate_grid.update", {
                            "node": self.unique_id,
                            "session_name": self.session_name,
                            "new_items": [meta],
                            "meta": self.existing_data["meta"]
                        })
                except ImportError:
                    pass
                
                self.total_decoded += 1
                #print(f"[GridTester] ✅ Remote VAE decoded #{meta['id']} ({self.total_decoded} total)")
                
            except Exception as e:
                #print(f"[GridTester] ❌ Remote VAE worker error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.queue.task_done()

    
    def add_job(self, latent_tensor, meta, height, width):
        """Add a decode job to the queue"""
        self.queue.put((latent_tensor, meta, height, width))
    
    def wait_completion(self):
        """Wait for all jobs to complete"""
        self.queue.join()
    
    def stop(self):
        """Stop the worker thread"""
        self.queue.put(None)
        self.thread.join()