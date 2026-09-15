"""Load a fairseq-trained wav2vec 2.0 "large" backbone into transformers.

Shared by the AntiDeepfake and XLSR-Mamba detectors. Both checkpoints embed the
same fairseq Wav2Vec2Model -- 24 layers x 1024, layer_norm_first, layer-norm
feature extractor, conv bias, 128/16 positional convolution -- just under
different key prefixes (m_ssl.model.* and ssl_model.model.*).

fairseq itself does not install cleanly on Python 3.12 / Windows. transformers'
Wav2Vec2Model with do_stable_layer_norm=True is the same network, so the weights
are renamed onto it (_RENAMES) instead. The load is strict: any weight the
network needs but the checkpoint lacks -- or any checkpoint weight with no place
in the network -- raises PortError rather than running with random weights.

The forward output (last_hidden_state) equals fairseq's
`model(wav, mask=False, features_only=True)['x']`: the final encoder layer after
the encoder's closing layer norm.
"""

from __future__ import annotations

import re


class PortError(RuntimeError):
    pass


# fairseq parameter names -> transformers Wav2Vec2Model names, applied in order.
_RENAMES = [
    (r"^feature_extractor\.conv_layers\.(\d+)\.0\.", r"feature_extractor.conv_layers.\1.conv."),
    (r"^feature_extractor\.conv_layers\.(\d+)\.2\.1\.", r"feature_extractor.conv_layers.\1.layer_norm."),
    (r"^layer_norm\.", "feature_projection.layer_norm."),
    (r"^post_extract_proj\.", "feature_projection.projection."),
    (r"^encoder\.pos_conv\.0\.", "encoder.pos_conv_embed.conv."),
    (r"\.self_attn_layer_norm\.", ".layer_norm."),
    (r"\.self_attn\.", ".attention."),
    (r"\.fc1\.", ".feed_forward.intermediate_dense."),
    (r"\.fc2\.", ".feed_forward.output_dense."),
]
# Pretraining-only heads: contrastive quantizer, projections and the mask
# embedding. Feature extraction with mask=False never touches them.
PRETRAINING_ONLY = ("quantizer.", "project_q.", "final_proj.", "mask_emb")


def hf_config():
    from transformers import Wav2Vec2Config

    # The fairseq large config both checkpoints were built with, every dropout
    # at zero for inference.
    return Wav2Vec2Config(
        hidden_size=1024, num_hidden_layers=24, num_attention_heads=16,
        intermediate_size=4096, hidden_act="gelu", feat_extract_activation="gelu",
        feat_extract_norm="layer", do_stable_layer_norm=True, conv_bias=True,
        conv_dim=(512,) * 7, conv_stride=(5, 2, 2, 2, 2, 2, 2),
        conv_kernel=(10, 3, 3, 3, 3, 2, 2),
        num_conv_pos_embeddings=128, num_conv_pos_embedding_groups=16,
        hidden_dropout=0.0, attention_dropout=0.0, activation_dropout=0.0,
        feat_proj_dropout=0.0, layerdrop=0.0, final_dropout=0.0,
        mask_time_prob=0.0, mask_feature_prob=0.0, apply_spec_augment=False,
        layer_norm_eps=1e-5,
    )


def rename(key: str) -> str:
    for pattern, repl in _RENAMES:
        key = re.sub(pattern, repl, key)
    return key


def build(fairseq_state: dict):
    """fairseq backbone weights (model prefix already stripped) -> an eval-mode
    transformers Wav2Vec2Model, loaded strictly."""
    from transformers import Wav2Vec2Model

    mapped = {rename(k): v for k, v in fairseq_state.items() if not k.startswith(PRETRAINING_ONLY)}
    model = Wav2Vec2Model(hf_config())
    expected = set(model.state_dict())

    # Positional-conv weight norm: older transformers names it weight_g /
    # weight_v, newer ones use torch parametrizations. Map to whichever exists.
    pos = "encoder.pos_conv_embed.conv."
    if f"{pos}weight_g" not in expected:
        for old, new in (("weight_g", "parametrizations.weight.original0"),
                         ("weight_v", "parametrizations.weight.original1")):
            if pos + old in mapped:
                mapped[pos + new] = mapped.pop(pos + old)

    missing = sorted(expected - set(mapped))
    unexpected = sorted(set(mapped) - expected)
    if missing or unexpected:
        raise PortError(
            f"backbone weights do not match the network: {len(missing)} missing "
            f"{missing[:4]}, {len(unexpected)} unexpected {unexpected[:4]}"
        )
    model.load_state_dict(mapped, strict=True)
    return model.eval()
