import json
import logging
import os
import sqlite3
import sys
from logging.handlers import RotatingFileHandler

import requests
from rich.logging import RichHandler
from you_get import common as you_get

hander = RotatingFileHandler("./logs/run.log",
                             encoding="UTF-8",
                             maxBytes=1024 * 1024 * 10,
                             backupCount=10)


class Bili_UP:
    """Bilibili UP Downloader"""

    def __init__(self, mid: str, log_level: str = "INFO"):
        """

        Args:
            mid (str): UP mid
        """
        logging.basicConfig(
            level=log_level.upper(),
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
            datefmt="%m-%d %H:%M",
            handlers=[RichHandler(rich_tracebacks=True, markup=True), hander])
        self.mid = mid
        self.haeders = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36",
            "Referer": "https://space.bilibili.com/%s" % self.mid,
            "Origin": "https://space.bilibili.com"
        }
        self.api_user_info = f'http://api.bilibili.com/x/space/acc/info?mid={mid}'
        self.api_video_list = f'http://api.bilibili.com/x/space/arc/search?mid={mid}&ps=30&pn='  # page number
        self.video_url = "https://www.bilibili.com/video/{0}"
        self.user_name = self.get_user_info()['data']['name']
        self.videos_path = './video/'

        self.log = logging.getLogger("Bili_UP " + self.user_name)
        self.log.info("[bold black on green] LOG LOAD SUCCESSFULLY [/]")
        self.log.info(f"[bold white on blue] RUN FOR {self.user_name} [/]")
        self.make_path(self.videos_path)
        self.video_list = []

        self.db = sqlite3.connect('./videos_info.sqlite')
        self.log.info('[bold black on green] DB CONNECT SUCCESSFULLY [/]')

    def get_user_info(self) -> json:
        """get user info

        Returns:
            json: user info
        """
        response = requests.get(self.api_user_info,headers=self.haeders)
        return response.json()

    def get_video_list(self):
        """get video list"""

        response = requests.get(self.api_video_list,headers=self.haeders)
        self.log.debug(response.json())
        count = response.json()['data']['page']['count']
        for i in range(count // 30 + 1):
            res = requests.get(self.api_video_list + str(i + 1),headers=self.haeders)
            self.log.debug(res.json())
            self.video_list += res.json()['data']['list']['vlist']

        self.log.info(
            f"[bold black on white] GET {len(self.video_list)} VIDEOS FOR {self.user_name} [/]"
        )
        self.insert_db()

    def insert_db(self):
        """insert video info to db"""
        cursor = self.db.cursor()
        for item in self.video_list:
            sql = """insert into video_info(aid,bvid,title,author,description,cover_img,pubtime,is_download) values ('%s','%s','%s','%s','%s','%s','%s','%s');""" % (
                item['aid'], item['bvid'], item['title'], item['author'],
                item['description'], item['pic'], item['created'], '0')
            try:
                cursor.execute(sql)
                self.db.commit()
                self.log.debug(
                    f"[bold black on green]INSERT {item['bvid']} SUCCESSFULLY[/]"
                )
            except sqlite3.IntegrityError:
                self.log.info(
                    f"[bold black on green] HAS DOWNLOADED [/][bold] {item['title']} [/]"
                )
                self.db.rollback()
            except sqlite3.OperationalError as e:
                self.log.error(f"[bold red on white]INSERT FAILED[/]")
                self.log.debug(sql)
                self.log.error(e)
                self.db.rollback()
        cursor.close()

    def downloader(self):
        """downloader"""
        cursor = self.db.cursor()
        sql = """select title,author,bvid,pubtime from video_info where is_download=0;"""
        cursor.execute(sql)
        data = cursor.fetchall()

        if len(data) == 0:
            self.log.info(f"[bold black on white] ALL VIDEOS DOWNLOADED [/]")
        else:
            for row in data:
                videos_dir = os.path.join(self.videos_path, row[1])
                self.make_path(videos_dir)
                video_file_path = os.path.join(videos_dir, row[0] + '.mp4')
                self.log.debug(f"video_file_path: {video_file_path}")
                if os.path.exists(video_file_path):
                    self.log.info(
                        f"[bold black on green] HAD BEEN DOWNLOADED SKIP [/][bold white on blue] {row[0]} [/]"
                    )
                    self.log.info(
                        f"[bold black on blue] FOR TIME SYNC START [/][bold white on blue] {row[0]} [/]"
                    )
                    self.change_time(video_file_path, row[3])
                    self.log.info(
                        f"[bold black on green] FOR TIME SYNC SUCCESSFULLY [/][bold white on blue] {row[0]} [/]"
                    )
                else:
                    self.check_download_count()
                    video_url = self.video_url.format(row[2])
                    self.log.debug(f"video_url -> {video_url}")
                    self.log.info(
                        f"[bold white on blue] {row[0]} [/][bold blue] START DOWNLOADING[/]"
                    )
                    sys.argv = [
                        'you-get', '-O', row[0], '-o', videos_dir, video_url
                    ]
                    you_get.main()
                    self.log.info(
                        f"[bold white on blue] {row[0]} [/][bold blue] TIME SYNC START[/]"
                    )
                    self.change_time(video_file_path, row[3])
                    self.log.info(
                        f"[bold green] TIME SYNC SUCCESSFULLY [/][bold white on blue] {row[0]} [/]"
                    )
                _sql = """update video_info SET is_download=1 where bvid='%s';""" % (
                    row[2])
                try:
                    cursor.execute(_sql)
                    self.db.commit()
                except:
                    self.db.rollback()
                self.log.info(
                    f"[bold green] DOWNLOADED [/][bold white on blue] {row[0]} [/]"
                )
                self.del_files(videos_dir)
        cursor.close()

    def change_time(self, file_path: str, time_stamp: int):
        """change file date and time sync to origin file time"""
        self.log.debug(f"file_path: {file_path}")
        os.utime(file_path, (time_stamp, time_stamp))

    def check_download_count(self):
        """check download count"""
        get_downloaded_count_sql = """select count(*) from video_info where is_download=1;"""
        get_all_count_sql = """select count(*) from video_info;"""
        cursor = self.db.cursor()
        cursor.execute(get_downloaded_count_sql)
        downloaded_count = cursor.fetchall()[0][0]
        cursor.execute(get_all_count_sql)
        all_count = cursor.fetchall()[0][0]
        self.log.info(
            f"[bold black on blue] VIDEOS INFO [/]: [bold black on green] ALL [/] [bold underline]{all_count}[/] [bold black on green] DOWNLOADED [/] [bold underline]{downloaded_count}[/] [bold white on red] NEED DOWNLOAD [/] [bold underline]{all_count-downloaded_count}[/]"
        )

    def del_files(self, root_dir: str, file_type: str = 'xml'):
        """DElETE FILES

        Args:
            file_type (str, optional): _description_. Defaults to 'xml'.
        """
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith(file_type):
                    os.remove(os.path.join(root, file))
                    self.log.info(f"[bold blue]{file} DELETED[/]")

    def make_path(self, path: str = "./video"):
        """make path

        Args:
            path (str, optional): _description_. Defaults to "./video".
        """
        if not os.path.exists(path):
            os.mkdir(path)
            self.log.debug(f"[bold green]{path} CREATED[/]")
        else:
            self.log.debug(f"[bold blue]{path} EXIST[/]")

    def run(self):
        """run"""
        self.get_video_list()
        self.downloader()
