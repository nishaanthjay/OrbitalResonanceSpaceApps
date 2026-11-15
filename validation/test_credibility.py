import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from rasterio.transform import Affine

import credibility as c

ROOT = Path(__file__).resolve().parents[1]
BIG = ROOT / "web/data/explore/big"


def test_class_metrics_formulas():
    m = c.class_metrics({"tp": 8, "fp": 2, "fn": 1, "tn": 4})
    assert m["n"] == 15
    assert m["forest_precision"] == pytest.approx(8 / 10)
    assert m["forest_recall"] == pytest.approx(8 / 9)
    assert m["nonforest_precision"] == pytest.approx(4 / 5)
    assert m["nonforest_recall"] == pytest.approx(4 / 6)
    assert m["overall_agreement"] == pytest.approx(12 / 15)
    assert m["confusion"]["map_nonforest"]["hansen_forest"] == 1


def test_class_metrics_match_scale_metrics_forest_side():
    met = json.loads((ROOT / "validation/scale_metrics.json").read_text())["a_forest_map"]["median"]
    m = c.class_metrics(met)
    assert m["forest_precision"] == pytest.approx(met["forest_precision"])
    assert m["forest_recall"] == pytest.approx(met["forest_recall"])
    assert m["overall_agreement"] == pytest.approx(met["oa"])


def test_decode_classes_and_persistence():
    img = np.zeros((1, 3, 4), np.uint8)
    img[0, 0] = (*c.FOREST_RGB, 255)
    img[0, 1] = (*c.NONFOREST_RGB, 255)
    cls = c.decode_classes(img)
    assert cls.tolist() == [[1, 2, 0]]
    stack = np.stack([cls] * 9)
    stack[0, 0, 1] = 1  # non-forest block forest on one pass
    assert c.persistence(stack).tolist() == [[9, 1, -1]]
    img[0, 2] = (1, 2, 3, 255)
    with pytest.raises(ValueError):
        c.decode_classes(img)


def test_categorise_and_distance():
    labels = np.zeros((5, 5), np.int32)
    labels[0, 0] = 1
    labels[4, 3:5] = 2
    alert = np.zeros((5, 5), bool)
    alert[4, 4] = True
    assert c.categorise(labels, alert) == {1: "radar_only_unconfirmed", 2: "alert_supported"}
    target = np.zeros((5, 5), bool)
    target[0, 1] = True
    d = c.distance_to(target, labels)
    assert d[1] == pytest.approx(100.0)
    assert d[2] == pytest.approx(c.BLOCK_M * np.hypot(4, 2))


def test_block_mapping_reproduces_lost_layer():
    big = json.loads((BIG / "big.json").read_text())
    gj = json.loads((BIG / "lost.geojson").read_text())
    tf = Affine(*big["grid"]["transform"])
    lost_disp = np.asarray(Image.open(BIG / big["layers"]["lost"]).convert("RGBA"))[..., 3] > 0
    blk = c.source_blocks(tf, *lost_disp.shape)
    back, rep = c.display_to_native(lost_disp.astype(np.uint8), blk, 0)
    labels = c.patch_labels(gj["features"])
    assert int((labels > 0).sum()) == sum(f["properties"]["n_blocks"] for f in gj["features"])
    assert np.array_equal(back == 1, (labels > 0) & rep)
