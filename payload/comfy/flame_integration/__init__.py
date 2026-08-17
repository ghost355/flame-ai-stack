# -*- coding: utf-8 -*-
"""
ComfyUI Custom Node: Flame Integration
Complete bidirectional integration between Autodesk Flame and ComfyUI
"""

import os

# Doit être défini AVANT tout import de cv2 (même indirect via ComfyUI)
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"

import json
import glob
import shutil
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image
import torch
import folder_paths
import server
from aiohttp import web

WEB_DIRECTORY = "./web"

# Valeurs par défaut — racine ComfyUI (fallback si aucune config trouvée)
_COMFY_BASE_DEFAULT = Path(__file__).parent.parent.parent
_EXPORT_DIR_DEFAULT = str(_COMFY_BASE_DEFAULT / "input" / "Flame_outputs")
_RETURN_DIR_DEFAULT = str(_COMFY_BASE_DEFAULT / "output" / "flame_returns")


def _get_flame_paths():
    """Chaîne de priorité pour les chemins d'échange Flame ↔ ComfyUI.

    1. ~/.comfy_flame_paths.json  — config propre à la machine ComfyUI
                                    (setup distant ou chemins personnalisés)
    2. ~/.flame_comfy_config.json — config Flame, utilisée quand Flame et
                                    ComfyUI sont sur la même machine
    3. Valeurs par défaut          — comportement original, aucune régression

    Format de ~/.comfy_flame_paths.json :
    {
        "export_dir": "/chemin/vers/input/Flame_outputs",
        "return_dir": "/chemin/vers/output/flame_returns"
    }
    """
    home = os.path.expanduser("~")

    # Niveau 1 : config propre à la machine ComfyUI
    comfy_cfg = os.path.join(home, ".comfy_flame_paths.json")
    if os.path.exists(comfy_cfg):
        try:
            with open(comfy_cfg, 'r') as f:
                cfg = json.load(f)
            export_dir = cfg.get('export_dir', _EXPORT_DIR_DEFAULT)
            return_dir = cfg.get('return_dir', _RETURN_DIR_DEFAULT)
            os.makedirs(return_dir, exist_ok=True)
            return export_dir, return_dir
        except Exception:
            pass

    # Niveau 2 : config Flame (même machine)
    flame_cfg = os.path.join(home, ".flame_comfy_config.json")
    if os.path.exists(flame_cfg):
        try:
            with open(flame_cfg, 'r') as f:
                cfg = json.load(f)
            export_dir = cfg.get('comfy_input_dir', _EXPORT_DIR_DEFAULT)
            return_dir = cfg.get('comfy_output_dir', _RETURN_DIR_DEFAULT)
            os.makedirs(return_dir, exist_ok=True)
            return export_dir, return_dir
        except Exception:
            pass

    # Niveau 3 : fallback
    os.makedirs(_RETURN_DIR_DEFAULT, exist_ok=True)
    return _EXPORT_DIR_DEFAULT, _RETURN_DIR_DEFAULT


_init_export_dir, _init_return_dir = _get_flame_paths()
print(f"[Flame Integration] Initialized:")
print(f"  Export Dir: {_init_export_dir}")
print(f"  Return Dir: {_init_return_dir}")


SELECTION_INDEX_OPTIONS = ["Last", "Last-1", "Last-2", "Last-3", "Last-4",
                           "Last-5", "Last-6", "Last-7", "Last-8", "Last-9"]


def parse_selection_index(s):
    """'Last' -> 0, 'Last-1' -> 1, 'Last-2' -> 2, etc."""
    if s == "Last":
        return 0
    try:
        return int(s.split("-")[1])
    except (IndexError, ValueError):
        return 0


def get_flame_folders(export_dir=None):
    """Get list of available Flame export folders.
    If export_dir is provided, use it directly; otherwise fall back to _get_flame_paths()."""
    if not export_dir:
        export_dir, _ = _get_flame_paths()
    folders = []
    if os.path.exists(export_dir):
        for item in os.listdir(export_dir):
            if item.startswith('.'):
                continue
            item_path = os.path.join(export_dir, item)
            if os.path.isdir(item_path):
                images = [f for f in os.listdir(item_path)
                         if f.lower().endswith(('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff'))]
                if images:
                    folders.append(item)

    # Sort by folder mtime (newest first), NOT by name — Flame names folders
    # like "40040" or "PR920564-B", so alphabetical order is meaningless and
    # "Last" would pick an old folder. mtime reflects actual export order.
    folders.sort(key=lambda f: os.path.getmtime(os.path.join(export_dir, f)), reverse=True)
    return folders if folders else [""]


class LoadFromFlame:
    """Load image sequences from Flame exports"""
    
    @classmethod
    def INPUT_TYPES(cls):
        folders = get_flame_folders()
        folder_hint = folders[0] if folders else ""
        return {
            "required": {
                "auto_load_latest": ("BOOLEAN", {"default": True}),
                "folder": ("STRING", {"default": folder_hint, "multiline": False,
                                      "tooltip": "Folder name inside export_dir. Injected automatically by Flame."}),
                "start_frame": ("INT", {"default": 0, "min": 0, "max": 10000}),
                "max_frames": ("INT", {"default": -1, "min": -1, "max": 10000}),
                "selection_index": (SELECTION_INDEX_OPTIONS, {"default": "Last"}),
            },
            "optional": {
                "export_dir": ("STRING", {"default": "", "multiline": False,
                                          "tooltip": "Override export dir (injected by Flame). Leave empty to use config."}),
            },
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "STRING")
    RETURN_NAMES = ("images", "masks", "frame_count", "source_name")
    FUNCTION = "load_sequence"
    CATEGORY = "Flame Integration"
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Force ComfyUI to always re-validate and re-execute this node"""
        import time
        return str(time.time())
    
    @classmethod
    def VALIDATE_INPUTS(cls, auto_load_latest, folder, start_frame, max_frames, selection_index, export_dir=""):
        """Custom validation - accept any folder name even if not in current list"""
        if not auto_load_latest and folder:
            resolved = export_dir.strip() if export_dir and export_dir.strip() else _get_flame_paths()[0]
            folder_path = os.path.join(resolved, folder)
            if not os.path.exists(folder_path):
                return f"Folder not found: {folder}"
        return True

    def load_sequence(self, auto_load_latest, folder, start_frame=0, max_frames=-1, selection_index="Last", export_dir=""):
        """Load image sequence from selected folder"""

        # Resolve export dir once — injected value takes priority over config
        resolved_export_dir = export_dir.strip() if export_dir and export_dir.strip() else _get_flame_paths()[0]

        # Si auto_load_latest, lister les dossiers depuis le bon chemin
        if auto_load_latest:
            folders = get_flame_folders(resolved_export_dir)
            if not folders or folders[0] == "":
                print(f"[Flame Load] No folders found in {resolved_export_dir}")
                return self._return_empty("No folders")

            idx = parse_selection_index(selection_index)

            if idx >= len(folders):
                print(f"[Flame Load] WARNING: {selection_index} (idx={idx}) but only {len(folders)} folder(s) available. Using last available.")
                idx = len(folders) - 1

            folder = folders[idx]
            print(f"[Flame Load] Auto-loading {selection_index} (idx={idx}): {folder}")

        if not folder:
            print(f"[Flame Load] No folder selected")
            return self._return_empty("No folder")

        export_path = os.path.join(resolved_export_dir, folder)

        if not os.path.exists(export_path):
            print(f"[Flame Load] ERROR: Folder not found: {export_path}")
            return self._return_empty(folder)
        
        return self._load_images_from_path(export_path, folder, start_frame, max_frames)
    
    def _return_empty(self, name):
        """Return empty tensors"""
        empty_img = torch.zeros((1, 64, 64, 3))
        empty_mask = torch.zeros((1, 64, 64))
        return {"ui": {"images": [], "frame_count": [0]}, "result": (empty_img, empty_mask, 0, name)}
    
    def _load_exr(self, filepath):
        """Load EXR file and return float32 RGB numpy array [0,1].
        Tries OpenCV first, then OpenImageIO, then OpenEXR."""
        
        # Try OpenCV (most common in ComfyUI environments)
        try:
            import cv2
            img = cv2.imread(filepath, cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
            if img is not None:
                # BGR to RGB
                if len(img.shape) == 3 and img.shape[2] >= 3:
                    img = img[:, :, :3][:, :, ::-1]  # BGR->RGB, drop alpha
                elif len(img.shape) == 2:
                    img = np.stack([img] * 3, axis=-1)
                img = img.astype(np.float32)
                img = np.clip(img, 0, 1)
                return img
        except ImportError:
            pass
        
        # Try OpenImageIO
        try:
            import OpenImageIO as oiio
            inp = oiio.ImageInput.open(filepath)
            if inp:
                spec = inp.spec()
                data = np.zeros((spec.height, spec.width, spec.nchannels), dtype=np.float32)
                inp.read_image(0, 0, oiio.FLOAT, data)
                inp.close()
                # Ensure 3 channels
                if data.shape[2] > 3:
                    data = data[:, :, :3]
                elif data.shape[2] == 1:
                    data = np.concatenate([data] * 3, axis=-1)
                return np.clip(data, 0, 1)
        except ImportError:
            pass
        
        # Try OpenEXR + Imath
        try:
            import OpenEXR
            import Imath
            exr = OpenEXR.InputFile(filepath)
            header = exr.header()
            dw = header['dataWindow']
            w = dw.max.x - dw.min.x + 1
            h = dw.max.y - dw.min.y + 1
            pt = Imath.PixelType(Imath.PixelType.FLOAT)
            
            channels = header['channels'].keys()
            if 'R' in channels and 'G' in channels and 'B' in channels:
                r = np.frombuffer(exr.channel('R', pt), dtype=np.float32).reshape(h, w)
                g = np.frombuffer(exr.channel('G', pt), dtype=np.float32).reshape(h, w)
                b = np.frombuffer(exr.channel('B', pt), dtype=np.float32).reshape(h, w)
                img = np.stack([r, g, b], axis=-1)
            elif 'Y' in channels:
                y = np.frombuffer(exr.channel('Y', pt), dtype=np.float32).reshape(h, w)
                img = np.stack([y, y, y], axis=-1)
            else:
                # Use first 3 channels available
                ch_names = sorted(channels)[:3]
                ch_data = [np.frombuffer(exr.channel(c, pt), dtype=np.float32).reshape(h, w) for c in ch_names]
                while len(ch_data) < 3:
                    ch_data.append(ch_data[0])
                img = np.stack(ch_data, axis=-1)
            
            return np.clip(img, 0, 1)
        except ImportError:
            pass
        
        print(f"[Flame Load] No EXR library available (cv2, OpenImageIO, or OpenEXR)")
        return None
    
    def _load_images_from_path(self, export_path, source_name, start_frame, max_frames):
        """Load images from path — supports PNG, JPG, EXR, TIFF.

        If the folder contains multiple image formats (e.g. stale EXR from an
        earlier export mixed with fresh PNG), only the format of the most
        recently modified file is loaded. This prevents frame duplication /
        mismatched sequences when Flame re-exports into an existing folder.
        """
        import glob as _glob
        candidate_exts = ['.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff']

        groups = {ext: [] for ext in candidate_exts}
        for ext in candidate_exts:
            for p in _glob.glob(os.path.join(export_path, f"*{ext}")):
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    mtime = 0.0
                groups[ext].append((p, mtime))

        latest_ext = None
        latest_mtime = -1.0
        for ext, entries in groups.items():
            for _, mtime in entries:
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_ext = ext

        if latest_ext is None:
            print(f"[Flame Load] ERROR: No images in {export_path}")
            return self._return_empty(source_name)

        image_files = [p for p, _ in groups[latest_ext]]
        print(f"[Flame Load] Using format {latest_ext} ({len(image_files)} files, "
              f"latest mtime {latest_mtime:.0f}) from {source_name}")

        image_files.sort()
        
        if not image_files:
            print(f"[Flame Load] ERROR: No images in {export_path}")
            return self._return_empty(source_name)
        
        if start_frame > 0:
            image_files = image_files[start_frame:]
        
        if max_frames > 0:
            image_files = image_files[:max_frames]
        
        print(f"[Flame Load] Loading {len(image_files)} frames from {source_name}")
        
        images = []
        masks = []
        
        for img_path in image_files:
            ext = os.path.splitext(img_path)[1].lower()
            
            if ext == '.exr':
                # EXR: try OpenCV first, then OpenImageIO
                img_array = self._load_exr(img_path)
                if img_array is None:
                    print(f"[Flame Load] ERROR: Cannot read EXR: {img_path}")
                    continue
                masks.append(np.ones((img_array.shape[0], img_array.shape[1]), dtype=np.float32))
                images.append(img_array)
            else:
                # PNG, JPG, TIFF: use Pillow
                img = Image.open(img_path)
                
                if img.mode != 'RGB':
                    if img.mode == 'RGBA':
                        mask = np.array(img.split()[-1]).astype(np.float32) / 255.0
                        masks.append(mask)
                        img = img.convert('RGB')
                    elif img.mode in ('I', 'I;16'):
                        # 16-bit grayscale or integer
                        img = img.convert('I')
                        img_array = np.array(img).astype(np.float32)
                        max_val = img_array.max()
                        if max_val > 1.0:
                            img_array = img_array / (65535.0 if max_val > 255 else 255.0)
                        # Convert grayscale to RGB
                        img_array = np.stack([img_array] * 3, axis=-1)
                        masks.append(np.ones((img_array.shape[0], img_array.shape[1]), dtype=np.float32))
                        images.append(img_array)
                        continue
                    elif img.mode == 'F':
                        # 32-bit float
                        img_array = np.array(img).astype(np.float32)
                        img_array = np.clip(img_array, 0, 1)
                        img_array = np.stack([img_array] * 3, axis=-1)
                        masks.append(np.ones((img_array.shape[0], img_array.shape[1]), dtype=np.float32))
                        images.append(img_array)
                        continue
                    else:
                        img = img.convert('RGB')
                        masks.append(np.ones((img.size[1], img.size[0]), dtype=np.float32))
                else:
                    masks.append(np.ones((img.size[1], img.size[0]), dtype=np.float32))
                
                img_array = np.array(img).astype(np.float32)
                # Normalize based on bit depth
                max_val = img_array.max()
                if max_val > 1.0:
                    img_array = img_array / (65535.0 if max_val > 255 else 255.0)
                images.append(img_array)
        
        if not images:
            print(f"[Flame Load] ERROR: No valid images loaded")
            return self._return_empty(source_name)
        
        images_tensor = torch.from_numpy(np.stack(images))
        masks_tensor = torch.from_numpy(np.stack(masks))
        
        print(f"[Flame Load] Loaded {len(images)} frames successfully")
        return {"ui": {"frame_count": [len(images)]}, "result": (images_tensor, masks_tensor, len(images), source_name)}


class SendToFlame:
    """Send processed images back to Flame with format options"""
    
    # Format specs: valid bit depths per format
    FORMAT_SPECS = {
        "exr":  {"depths": ["16f", "32f"], "ext": ".exr"},
        "png":  {"depths": ["8", "16"], "ext": ".png"},
        "tiff": {"depths": ["8", "16", "32f"], "ext": ".tif"},
        "jpg":  {"depths": ["8"], "ext": ".jpg"},
        "mov":  {"depths": ["16f"], "ext": ".mov"},
    }
    
    # EXR compression options
    EXR_COMPRESSIONS = ["none", "zip", "zips", "rle", "pxr24", "dwaa"]
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "flame_output"}),
                "file_type": (["exr", "png", "tiff", "jpg", "mov"], {"default": "exr"}),
                "bit_depth": (["8", "16", "16f", "32f"], {"default": "16"}),
            },
            "optional": {
                "workflow_name": ("STRING", {"default": ""}),
                "clip_name": ("STRING", {"default": ""}),
                "return_dir": ("STRING", {"default": "",
                                          "tooltip": "Override return dir (injected by Flame). Leave empty to use config."}),
                "pipeline_result_path": ("STRING", {"default": ""}),
                "exr_compression": (["zip", "zips", "none", "rle", "pxr24", "dwaa"], {"default": "zip"}),
                "jpg_quality": ("INT", {"default": 100, "min": 1, "max": 100}),
                "colorspace": (["linear", "sRGB", "ACEScg"], {"default": "linear"}),
                "frame_padding": ("INT", {"default": 4, "min": 1, "max": 8}),
                "fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 120.0, "step": 1.0,
                                  "tooltip": "Frame rate for .mov (ProRes 4444) output. Match your clip's fps."}),
                "colour_space": (["bt709", "srgb", "p3"], {"default": "bt709",
                                  "tooltip": "Colour space tag written into ProRes 4444 metadata (injected by Flame). Must match the source clip."}),
            }
        }
    
    RETURN_TYPES = ()
    FUNCTION = "send_to_flame"
    OUTPUT_NODE = True
    CATEGORY = "Flame Integration"
    
    def _validate_bit_depth(self, file_type, bit_depth):
        """Validate bit depth for the chosen format, fallback to first valid"""
        valid = self.FORMAT_SPECS[file_type]["depths"]
        if bit_depth in valid:
            return bit_depth
        print(f"[Flame Return] Warning: {bit_depth} not valid for {file_type}, using {valid[0]}")
        return valid[0]
    
    def _save_exr(self, img_np, filepath, bit_depth, compression):
        """Save EXR using OpenEXR if available, fallback to Pillow 32-bit"""
        try:
            import OpenEXR
            import Imath
            
            h, w = img_np.shape[:2]
            channels = img_np.shape[2] if img_np.ndim == 3 else 1
            
            if bit_depth == "16f":
                pixel_type = Imath.PixelType(Imath.PixelType.HALF)
                data = img_np.astype(np.float16)
            else:
                pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)
                data = img_np.astype(np.float32)
            
            # Map compression names
            comp_map = {
                "none": Imath.Compression(Imath.Compression.NO_COMPRESSION),
                "zip": Imath.Compression(Imath.Compression.ZIP_COMPRESSION),
                "zips": Imath.Compression(Imath.Compression.ZIPS_COMPRESSION),
                "rle": Imath.Compression(Imath.Compression.RLE_COMPRESSION),
                "pxr24": Imath.Compression(Imath.Compression.PXR24_COMPRESSION),
                "dwaa": Imath.Compression(Imath.Compression.DWAA_COMPRESSION),
            }
            
            header = OpenEXR.Header(w, h)
            header['compression'] = comp_map.get(compression, comp_map["zips"])
            
            if channels >= 3:
                # RGB(A) - premultiply alpha (OpenEXR standard: Flame expects RGB*A)
                write_data = data.copy()
                if channels >= 4:
                    alpha = write_data[:, :, 3:4]
                    write_data[:, :, :3] *= alpha
                channel_data = {}
                channel_names = ['R', 'G', 'B', 'A'][:channels]
                for i, name in enumerate(channel_names):
                    ch = write_data[:, :, i].tobytes()
                    channel_data[name] = ch
                    header['channels'][name] = Imath.Channel(pixel_type)
                
                exr_file = OpenEXR.OutputFile(filepath, header)
                exr_file.writePixels(channel_data)
                exr_file.close()
            else:
                # Single channel
                header['channels'] = {'Y': Imath.Channel(pixel_type)}
                exr_file = OpenEXR.OutputFile(filepath, header)
                exr_file.writePixels({'Y': data.squeeze().tobytes()})
                exr_file.close()
            
            return True
            
        except ImportError:
            print("[Flame Return] OpenEXR not available, trying OpenImageIO...")
            
            try:
                import OpenImageIO as oiio
                
                h, w = img_np.shape[:2]
                channels = img_np.shape[2] if img_np.ndim == 3 else 1
                
                if bit_depth == "16f":
                    data = np.ascontiguousarray(img_np.astype(np.float16))
                    pixel_type = oiio.HALF
                else:
                    data = np.ascontiguousarray(img_np.astype(np.float32))
                    pixel_type = oiio.FLOAT
                
                spec = oiio.ImageSpec(w, h, channels, pixel_type)
                spec.attribute("compression", compression)
                
                buf = oiio.ImageBuf(spec)
                buf.set_pixels(oiio.ROI(), data)
                
                if not buf.write(filepath):
                    raise RuntimeError(f"OIIO write failed: {oiio.geterror()}")
                
                return True
                
            except ImportError:
                print("[Flame Return] No EXR library available — saving as PNG 16-bit fallback")
                return False
    
    def _save_prores(self, frames, filepath, fps=25, colour_space="bt709"):
        """Save RGBA frames as ProRes 4444 (.mov) via PyAV — native Flame format with alpha.
        
        ProRes 4444 (profile 4, yuva444p10le) carries an alpha channel that Flame
        imports natively, unlike EXR sequences where alpha must be explicitly enabled.
        Frames arrive premultiplied (RGB*A) — the alpha is kept as-is, matching how
        Flame treats ProRes 4444 output from its own export.
        """
        try:
            import av
            
            container = av.open(filepath, mode='w')
            stream = container.add_stream('prores_ks', rate=int(fps))  # PyAV 17 rejects float rate
            stream.options['profile'] = '4'  # ProRes 4444 (with alpha)
            stream.pix_fmt = 'yuva444p10le'
            cs = {"bt709": 1, "srgb": 1, "p3": 9}.get(colour_space, 1)
            stream.colorspace = cs  # BT.709 or P3
            stream.color_primaries = cs
            stream.color_trc = cs
            stream.width = frames[0].shape[1]
            stream.height = frames[0].shape[0]
            
            for img_np in frames:
                h, w = img_np.shape[:2]
                if img_np.ndim == 2:
                    img_np = np.stack([img_np] * 3, axis=-1)
                if img_np.shape[2] == 3:
                    # No alpha — pad with opaque alpha
                    img_np = np.concatenate([img_np, np.ones((h, w, 1), dtype=img_np.dtype)], axis=-1)
                rgba = np.clip(img_np[:, :, :4], 0, 1)
                rgba[:, :, :3] *= rgba[:, :, 3:4]  # Premultiply RGB by alpha — Flame composites premultiplied clips correctly by default
                rgba = (rgba * 65535).astype(np.uint16)
                frame = av.VideoFrame.from_ndarray(rgba, format='rgba64le')
                for packet in stream.encode(frame):
                    container.mux(packet)
            
            for packet in stream.encode():
                container.mux(packet)
            container.close()
            return True
            
        except ImportError:
            print("[Flame Return] PyAV not available — cannot write ProRes 4444")
            return False
    
    def _save_png(self, img_np, filepath, bit_depth):
        """Save PNG 8-bit or 16-bit"""
        if bit_depth == "16":
            data = np.clip(img_np * 65535, 0, 65535).astype(np.uint16)
            if data.ndim == 3 and data.shape[2] == 1:
                # Grayscale 16-bit — Pillow handles this
                Image.fromarray(data[:, :, 0], mode='I;16').save(filepath)
            elif data.ndim == 3 and data.shape[2] == 3:
                # RGB 16-bit — cv2 is required; Pillow cannot handle uint16 RGB
                try:
                    import cv2
                    bgr = np.ascontiguousarray(data[:, :, ::-1])  # RGB→BGR
                    cv2.imwrite(filepath, bgr)
                    return
                except ImportError:
                    pass
                # cv2 not available — fall back to 8-bit
                data8 = np.clip(img_np * 255, 0, 255).astype(np.uint8)
                Image.fromarray(data8).save(filepath)
                print("[Flame Return] Warning: 16-bit RGB PNG needs cv2, saved as 8-bit")
            else:
                data8 = np.clip(img_np * 255, 0, 255).astype(np.uint8)
                Image.fromarray(data8).save(filepath)
        else:
            # 8-bit standard
            data = np.clip(img_np * 255, 0, 255).astype(np.uint8)
            Image.fromarray(data).save(filepath)
    
    def _save_tiff(self, img_np, filepath, bit_depth):
        """Save TIFF via Pillow or tifffile"""
        try:
            import tifffile
            if bit_depth == "32f":
                tifffile.imwrite(filepath, img_np.astype(np.float32))
            elif bit_depth == "16":
                data = np.clip(img_np * 65535, 0, 65535).astype(np.uint16)
                tifffile.imwrite(filepath, data)
            else:
                data = np.clip(img_np * 255, 0, 255).astype(np.uint8)
                tifffile.imwrite(filepath, data)
            return
        except ImportError:
            pass
        
        # Fallback to Pillow (8-bit only)
        data = np.clip(img_np * 255, 0, 255).astype(np.uint8)
        img = Image.fromarray(data)
        img.save(filepath)
        if bit_depth != "8":
            print(f"[Flame Return] Warning: tifffile not available, saved TIFF as 8-bit")
    
    def _save_jpg(self, img_np, filepath, quality):
        """Save JPEG 8-bit"""
        data = np.clip(img_np * 255, 0, 255).astype(np.uint8)
        img = Image.fromarray(data)
        img.save(filepath, quality=quality, subsampling=0)  # 4:4:4 subsampling
    
    def send_to_flame(self, images, filename_prefix="flame_output", file_type="exr",
                       bit_depth="16", workflow_name="", clip_name="",
                       return_dir="", pipeline_result_path="", exr_compression="zip",
                       jpg_quality=100, colorspace="linear", frame_padding=4, fps=25.0,
                       colour_space="bt709"):
        """Save images and notify Flame"""
        
        # Fallback for empty values (from old workflows without these fields)
        if not file_type or file_type not in self.FORMAT_SPECS:
            file_type = "exr"
            print(f"[Flame Return] file_type empty or invalid, defaulting to: {file_type}")
        if not bit_depth or bit_depth not in ["8", "16", "16f", "32f"]:
            bit_depth = "16"
            print(f"[Flame Return] bit_depth empty or invalid, defaulting to: {bit_depth}")
        
        # Validate bit depth for format
        bit_depth = self._validate_bit_depth(file_type, bit_depth)
        ext = self.FORMAT_SPECS[file_type]["ext"]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        base_name = clip_name if clip_name else (workflow_name if workflow_name else filename_prefix)
        folder_name = f"{base_name}_{timestamp[-4:]}"

        resolved_return_dir = return_dir.strip() if return_dir and return_dir.strip() else _get_flame_paths()[1]
        output_folder = os.path.join(resolved_return_dir, folder_name)
        os.makedirs(output_folder, exist_ok=True)
        
        saved_files = []
        exr_fallback_to_png = False

        # .mov (ProRes 4444) is a single video file containing all frames,
        # not an image sequence — encode all frames at once before the loop.
        if file_type == "mov":
            frames = []
            for image in images:
                img_np = image.cpu().numpy().astype(np.float32)
                img_np = np.clip(img_np, 0, 1)
                if img_np.ndim == 2:
                    img_np = img_np[:, :, np.newaxis]
                frames.append(img_np)
            filename = f"{filename_prefix}_{timestamp}{ext}"
            filepath = os.path.join(output_folder, filename)
            try:
                self._save_prores(frames, filepath, fps, colour_space)
                saved_files.append(filename)
                print(f"[Flame Return] Saved: {filepath}")
            except Exception as e:
                print(f"[Flame Return] Error saving ProRes: {e}")
                file_type = "exr"
                ext = ".exr"
                bit_depth = self._validate_bit_depth("exr", bit_depth)
        
        for idx, image in enumerate(images):
            # Convert tensor to float32 numpy [0,1]
            img_np = image.cpu().numpy().astype(np.float32)
            img_np = np.clip(img_np, 0, 1)
            
            # Ensure 3D (H, W, C)
            if img_np.ndim == 2:
                img_np = img_np[:, :, np.newaxis]
            
            # Build filename with frame padding
            if len(images) > 1:
                frame_str = str(idx).zfill(frame_padding)
                filename = f"{filename_prefix}_{timestamp}.{frame_str}{ext}"
            else:
                filename = f"{filename_prefix}_{timestamp}{ext}"
            
            filepath = os.path.join(output_folder, filename)
            
            # Save based on format
            if file_type == "exr":
                success = self._save_exr(img_np, filepath, bit_depth, exr_compression)
                if not success:
                    # Fallback to PNG 16-bit
                    exr_fallback_to_png = True
                    ext = ".png"
                    filepath = filepath.replace(".exr", ".png")
                    filename = filename.replace(".exr", ".png")
                    self._save_png(img_np, filepath, "16")
            elif file_type == "png":
                self._save_png(img_np, filepath, bit_depth)
            elif file_type == "tiff":
                self._save_tiff(img_np, filepath, bit_depth)
            elif file_type == "jpg":
                self._save_jpg(img_np, filepath, jpg_quality)
            
            saved_files.append(filename)
            print(f"[Flame Return] Saved: {filepath}")
        
        if exr_fallback_to_png:
            print("[Flame Return] EXR libs not available — saved as PNG 16-bit")
        
        # Build notification
        notification = {
            "timestamp": timestamp,
            "workflow_name": workflow_name if workflow_name else "unknown",
            "clip_name": clip_name if clip_name else base_name,
            "output_folder": folder_name,
            "files": saved_files,
            "frame_count": len(saved_files),
            "file_type": file_type if not exr_fallback_to_png else "png",
            "bit_depth": bit_depth,
            "colorspace": colorspace,
            "status": "ready"
        }
        
        # Save notification to local output dir
        notification_file = os.path.join(resolved_return_dir, 'notification.json')
        with open(notification_file, 'w') as f:
            json.dump(notification, f, indent=2)
        
        print(f"[Flame Return] Notification created (local)")
        
        # If pipeline_result_path is set, also save results + notification there
        if pipeline_result_path and pipeline_result_path.strip():
            try:
                pipeline_folder = os.path.join(pipeline_result_path.strip(), folder_name)
                os.makedirs(pipeline_folder, exist_ok=True)
                
                for fname in saved_files:
                    src = os.path.join(output_folder, fname)
                    shutil.copy2(src, pipeline_folder)
                
                pipeline_notification = os.path.join(pipeline_result_path.strip(), 'notification.json')
                pipeline_notif = notification.copy()
                pipeline_notif['pipeline_folder'] = pipeline_folder
                with open(pipeline_notification, 'w') as f:
                    json.dump(pipeline_notif, f, indent=2)
                
                print(f"[Flame Return] Pipeline copy: {pipeline_folder}")
                
            except Exception as e:
                print(f"[Flame Return] Pipeline copy failed: {e}")
        
        format_info = f"{file_type.upper()} {bit_depth}-bit"
        if file_type == "exr":
            format_info += f" ({exr_compression})"
        
        print(f"[Flame Return] {len(saved_files)} images ready for Flame [{format_info}]")
        
        return {"ui": {"text": [f"Sent {len(saved_files)} {format_info} images to Flame"]}}


NODE_CLASS_MAPPINGS = {
    "FlameLoad": LoadFromFlame,
    "FlameSend": SendToFlame,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlameLoad": "Load from Flame",
    "FlameSend": "Send to Flame",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]


# API routes
@server.PromptServer.instance.routes.get("/flame/folder_images")
async def get_folder_images(request):
    folder = request.rel_url.query.get("folder", "")
    max_frames = int(request.rel_url.query.get("max_frames", "20"))

    if not folder or ".." in folder:
        return web.json_response({"error": "Invalid folder"}, status=400)

    export_dir, _ = _get_flame_paths()
    folder_path = os.path.join(export_dir, folder)
    if not os.path.isdir(folder_path):
        return web.json_response({"error": "Folder not found"}, status=404)

    image_files = []
    for ext in ['.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff']:
        image_files.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))
    image_files.sort()

    if not image_files:
        return web.json_response({"error": "No images"}, status=404)

    total_frames = len(image_files)

    if max_frames > 0 and total_frames > max_frames:
        step = total_frames / max_frames
        image_files = [image_files[int(i * step)] for i in range(max_frames)]

    filenames = [os.path.basename(f) for f in image_files]

    return web.json_response({
        "total_frames": total_frames,
        "preview_frames": len(filenames),
        "images": filenames
    })


@server.PromptServer.instance.routes.get("/flame/folders")
async def get_folders_list(request):
    export_dir, _ = _get_flame_paths()
    folders = get_flame_folders(export_dir)
    folders = [f for f in folders if f]
    return web.json_response({"folders": folders})


@server.PromptServer.instance.routes.get("/flame/preview_thumb")
async def get_preview_thumb(request):
    import io as _io
    folder = request.rel_url.query.get("folder", "")
    index = int(request.rel_url.query.get("index", "0"))

    if not folder or ".." in folder:
        return web.Response(status=400)

    export_dir, _ = _get_flame_paths()
    folder_path = os.path.join(export_dir, folder)
    if not os.path.isdir(folder_path):
        return web.Response(status=404)

    image_files = []
    for ext in ['.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff']:
        image_files.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))
    image_files.sort()

    if not image_files:
        return web.Response(status=404)

    index = min(index, len(image_files) - 1)
    filepath = image_files[index]
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == '.exr':
            node = LoadFromFlame()
            img_array = node._load_exr(filepath)
            if img_array is None:
                return web.Response(status=500)
            if img_array.ndim == 2:
                img_array = np.stack([img_array] * 3, axis=-1)
            elif img_array.shape[2] == 1:
                img_array = np.concatenate([img_array] * 3, axis=-1)
            elif img_array.shape[2] > 3:
                img_array = img_array[:, :, :3]
            max_val = img_array.max()
            if max_val > 1.0:
                img_array = img_array / max_val
            data = (np.clip(img_array, 0, 1) * 255).astype(np.uint8)
            buf = _io.BytesIO()
            Image.fromarray(data, 'RGB').save(buf, format='JPEG', quality=85)
            return web.Response(body=buf.getvalue(), content_type='image/jpeg')
        elif ext in ('.jpg', '.jpeg'):
            with open(filepath, 'rb') as f:
                return web.Response(body=f.read(), content_type='image/jpeg')
        else:
            img = Image.open(filepath).convert('RGB')
            buf = _io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            return web.Response(body=buf.getvalue(), content_type='image/jpeg')
    except Exception as e:
        print(f"[Flame] preview_thumb error: {e}")
        return web.Response(status=500)


