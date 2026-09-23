"""
HuggingFace model adapters for VARUNA AI.

All models implement the `RainfallModel` interface (ai_models/base.py) so they are
drop-in replacements for the existing tabular and satellite models.

Quick start
-----------
>>> from ai_models.hf_models.registry import list_models, build_tabular_model, build_vision_model
>>> list_models()
>>> model = build_tabular_model("tabpfn")   # zero-shot, no training needed
>>> model = build_vision_model("swin-tiny") # pretrained ImageNet weights, fine-tune head only
"""
