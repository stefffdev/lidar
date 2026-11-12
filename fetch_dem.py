#!/usr/bin/env python3
"""Download a square of the Austrian 1 m lidar terrain model (BEV ALS DTM).

The BEV publishes the model as huge Cloud Optimized GeoTIFFs (50 km tiles,
EPSG:3035). Only the requested window is read, via HTTP range requests.
The window is resampled to a north-up 1 m UTM 33N grid and written to
data/dem.u16 (+ data/meta.json) for the viewer in index.html.

    .venv/bin/python fetch_dem.py [--lat 47.1954 --lon 15.5759 --size 4096]
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform, transform_bounds

BASE = "https://data.bev.gv.at/download/ALS/DTM/{date}/ALS_DTM_CRS3035RES50000mN{n}E{e}.tif"
TILE = 50_000
DST_CRS = "EPSG:32633"  # UTM 33N: metres, north-up to within ~0.5 deg here


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lat", type=float, default=47.19537164797733)
    ap.add_argument("--lon", type=float, default=15.575889718104298)
    ap.add_argument("--size", type=int, default=10000, help="edge length in metres (= pixels)")
    ap.add_argument("--date", default="20250915", help="BEV release (Stichtag), e.g. 20240915")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    size = args.size
    xs, ys = transform("EPSG:4326", DST_CRS, [args.lon], [args.lat])
    left = round(xs[0]) - size // 2
    top = round(ys[0]) + size // 2
    dst_transform = from_origin(left, top, 1.0, 1.0)

    # Which 50 km source tiles does the window touch?
    w, s, e, n = transform_bounds(DST_CRS, "EPSG:3035", left, top - size, left + size, top)
    tiles = [
        (tn, te)
        for tn in range(int(s // TILE) * TILE, int(n // TILE) * TILE + 1, TILE)
        for te in range(int(w // TILE) * TILE, int(e // TILE) * TILE + 1, TILE)
    ]

    dem = np.full((size, size), np.nan, dtype=np.float32)
    env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    )
    with env:
        for tn, te in tiles:
            url = BASE.format(date=args.date, n=tn, e=te)
            print("reading", url)
            try:
                src = rasterio.open(url)
            except rasterio.errors.RasterioIOError as err:
                print("  skipped:", err)
                continue
            with src, WarpedVRT(
                src,
                crs=DST_CRS,
                transform=dst_transform,
                width=size,
                height=size,
                resampling=Resampling.cubic,
                dst_nodata=np.nan,
            ) as vrt:
                part = vrt.read(1).astype(np.float32)
            if src.nodata is not None:
                part[part == src.nodata] = np.nan
            dem = np.where(np.isnan(dem), part, dem)

    missing = int(np.isnan(dem).sum())
    if missing == dem.size:
        raise SystemExit("No data found - is the location inside Austria?")
    zmin, zmax = float(np.nanmin(dem)), float(np.nanmax(dem))
    if missing:
        print(f"note: {missing} pixels without data were filled with the minimum height")
        dem = np.nan_to_num(dem, nan=zmin)

    # 16 bit, centimetre steps where the height range allows it
    scale = max(0.01, (zmax - zmin) / 65535)
    packed = np.round((dem - zmin) / scale).astype("<u2")

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    packed.tofile(out / "dem.u16")
    meta = {
        "width": size,
        "height": size,
        "cell": 1.0,
        "offset": zmin,
        "scale": scale,
        "lat": args.lat,
        "lon": args.lon,
        "home": {"col": xs[0] - left, "row": top - ys[0]},
        "year": args.date[:4],
        "attribution": "BEV ALS DTM 1 m, CC BY 4.0",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {out}/dem.u16  {size}x{size} px, heights {zmin:.1f} - {zmax:.1f} m")


if __name__ == "__main__":
    main()
