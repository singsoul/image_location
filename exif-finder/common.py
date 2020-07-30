import copy
import itertools
import os
import pathlib
import time
from contextlib import contextmanager
from fractions import Fraction

import moment

from conf import config
from log import error, info


@contextmanager
def checkTimes(msg: str = "", level: int = 3):
    """
        检查处理花费时间
    """
    start_time = time.time()
    yield
    info(f"{msg} 时间: {round(time.time()-start_time,level)}s")


def jpg_walk(path: str, filter_types: list) -> list:
    """
        获取指导目录全部的图片路径
    """
    with checkTimes("抓取完成"):
        pools = list(filter(
            lambda _: config.exif_result_path_name not in str(_),
            itertools.chain(
                *[
                    list(pathlib.Path(path).glob(f"**/*.{types}"))
                    for types in filter_types
                ]
            )
            
        ))
        info(f"发现图片: {len(pools)}")
        return pools


def radio_format(data):
    """
        强制转分数
    """
    return [Fraction(item.num, item.den) for item in data]


def gps_format(loc: list) -> float:
    """
        经纬度格式转换 度分秒转小数
    """
    loc = radio_format(loc)
    return float(loc[0] + Fraction(loc[1], 60) + Fraction(loc[2], 3600))


def ref_format(ref):
    """
        方向转换
    """
    return 1 if ref.upper() in ["N", "E"] else -1


def real_gps(tags):
    """
        获取经纬度
    """
    for lat, lon in config.gps_tag:
        if all(map(lambda item: item in tags, itertools.chain(lat, lon))):
            gps = [
                gps_format(tags[lat[0]].values) * ref_format(tags[lat[1]].values),
                gps_format(tags[lon[0]].values) * ref_format(tags[lon[1]].values),
            ]
            if gps:
                return gps


def real_time(tags):
    """
        获取特定时间
    """
    tag_keys = tags.keys()
    items = list(set(config.time_list) & set(tag_keys))
    if items:
        dates = str(tags[items[0]]).split()
        dates[0] = dates[0].replace(":", "-")
        return " ".join(dates)
    else:
        return ""


def real_alt(tags):
    """
        获取高度
    """
    default_alt = (0.0, "海平面")
    tag_keys = tags.keys()
    alt, ref = config.alt_tag
    if alt in tag_keys:
        try:
            alt_num = eval(str(tags[alt].values[0]))
        except ZeroDivisionError:
            alt_num = 0
        default_alt = (
            round(alt_num, 2),
            ("地面" if radio_format(tags[ref].values)[0] == 1 else "海平面"),
        )
    return default_alt


def checkPath(path):
    return os.path.exists(path)


def initPath(path):
    if not checkPath(path):
        os.makedirs(path)
        path += " [已创建!]"
    return path


def make_popup(item):
    """
        投射坐标点
    """
    add_normal = (
        lambda data, dicts: f"<p>{data[1]}: {dicts[data[0]]}</p>"
        if data[0] in dicts
        else ""
    )
    html = ""
    cols = (("address", "地址"), ("make", "设备"), ("model", "型号"), ("soft", "编辑软件"))

    if "path" in item:
        html += '<center><p> <a href="{}">{}</a ></p></center>'.format(
            item["path"], item["path"]
        )
    if "date" in item:
        html += f"<center><p>{item['date']}</p></center>"
    if "path" in item:
        html += "<img src='{}' height='240' width='240' />".format(item["new_path"])
    html += "".join([add_normal(_, item) for _ in cols])
    if "alt" in item and item["alt"][0] > 0.0:
        html += "<p>高度: {1} {0}米</p>".format(*item["alt"])
    return html
