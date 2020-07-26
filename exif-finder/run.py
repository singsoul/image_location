import hashlib
import json
import os
import pathlib
import random
import shutil
import time

import asks
import click
import exifread
import progressbar
import moment
import trio

from common import (
    checkPath,
    initPath,
    jpg_walk,
    real_alt,
    real_gps,
    real_time,
)
from conf import config
from exporter import analysis, create_json
from log import error, info, success, warning

asks.init("trio")


class Finder:
    def __init__(self):
        self.limit = trio.CapacityLimiter(config.conns * 5)
        self.address_details_url = (
            "http://restapi.amap.com/v3/geocode/regeo?key={}&s=rsv3&location={},{}"
        )
        self.image_pools = {}
        self.res_pools = {}
        self.event_path = f"{config.exif_result_path_name}/{moment.now().format('YYYY-MM-DD hh:mm:ss')}"
        info(f"事件路径: {initPath(self.event_path)}")
        self.image_path = os.path.join(self.event_path, "images")
        if config.save_image:
            info(f"图片路径: {initPath(self.image_path)}")

    async def init_session(self):
        """
            初始化session
        """
        self.session = asks.Session(connections=config.conns)
        self.session.header = {
            "User-Agent": random.choice(config.ua_list),
            "Accept": "text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate, sdch",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Referer": "http://www.gpsspg.com",
        }

    def get_exif_datas(self, path, num):
        """
            获取图片内的exif信息
        """
        with path.open("rb") as file:
            info = {"path": path, "date": ""}
            try:
                tags = exifread.process_file(file, strict=True)
                if tags:
                    info["gps"] = real_gps(tags)
                    if not info["gps"]:
                        return
                    info["alt"] = real_alt(tags)
                    info["date"] = real_time(tags)
                    for name, nickname in config.show_list:
                        if name in tags.keys():
                            info[nickname] = tags[name].values
                    self.res_pools[
                        hashlib.new("md5", path.name.encode()).hexdigest()
                    ] = info
            except Exception as e:
                pass
            finally:
                self.bar.update(num)

    async def find_address(self, key, item):
        """
            获取地理位置信息
        """
        async with self.limit:
            gps = item["gps"]
            resp = await self.session.get(
                self.address_details_url.format(config.rest_api_key, gps[1], gps[0])
            )
            datas = resp.json()
            if datas and datas["status"] == "1" and datas["info"].lower() == "ok":
                self.res_pools[key]["address"] = datas.get("regeocode", {}).get(
                    "formatted_address", ""
                )

    async def find_all_address(self):
        """
            获取全部的地理位置信息
        """
        info("查询地理位置中...")
        async with trio.open_nursery() as nursery:
            for key, item in self.res_pools.items():
                nursery.start_soon(self.find_address, key, item)

    def run(self):
        """
            主运行方法
        """
        checkPath(config.target_path)
        self.image_pools = jpg_walk(config.target_path, config.types_filter)
        self.bar = progressbar.ProgressBar(max_value=len(self.image_pools))
        times = 0
        while self.image_pools:
            times += 1
            self.get_exif_datas(self.image_pools.pop(), times)
        if config.location and config.rest_api_key:
            trio.run(self.init_session)
            trio.run(self.find_all_address)
        if config.save_image:
            info("拷贝图片...")
            for index, (key, item) in enumerate(self.res_pools.items()):
                to_file = pathlib.Path(
                    self.image_path,
                    ".".join([str(index), item["path"].name.split(".")[-1]]),
                )
                shutil.copy(str(item["path"]), str(to_file))
                self.res_pools[key]["new_path"] = "/".join(
                    str(to_file).split("/")[2:]
                )
        datas = sorted(
            [item for _, item in self.res_pools.items() if item and item["date"]],
            key=lambda i: i.get("date", ""),
        )
        if not datas:
            exit("结果为空")
        if config.analysis:
            analysis(datas, f"{self.event_path}/res.html")
        for item in datas:
            item["path"] = str(item["path"].absolute())
        create_json(datas, f"{self.event_path}/res.json")


@click.command()
@click.argument("target_path")
@click.option("-s", "--save_image", is_flag=True, help="是否保图片")
@click.option("-l", "--location", is_flag=True, help="是否启用地理定位")
@click.option("-a", "--analysis", is_flag=True, prompt="是否启用结果分析", help="是否启用结果分析")
@click.option("--dark", is_flag=True, help="是否启用暗黑风格地图")
@click.option("--locus", is_flag=True, help="是否启用时间路线")
def main(
    target_path: str,
    save_image: str,
    location: bool,
    analysis: bool,
    dark: bool,
    locus: bool,
):
    
    click.echo(f"搜索路径={target_path}")
    config.target_path = target_path
    if save_image:
        # click.echo(f"保存路径={save_image}")
        config.save_image = save_image
    if location:
        click.echo(f"是否定位地址={location}")
        if config.rest_api_key:
            config.location = location
        else:
            warning("你需要申请API Key :https://lbs.amap.com/")
    if analysis:
        # click.echo(f"是否分析结果={analysis}")
        config.analysis = analysis
        config.save_image = True
    if dark:
        config.dark_mode = dark
    if locus:
        config.locus = locus
    Finder().run()


if __name__ == "__main__":
    main()
