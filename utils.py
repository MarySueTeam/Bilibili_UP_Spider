import requests
import logging
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
import sqlite3
import sys
from you_get import common as you_get
import os
from rich.progress import track

hander = RotatingFileHandler("./logs/run.log",
                             encoding="UTF-8",
                             maxBytes=1024 * 1024 * 10,
                             backupCount=10)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt="%m-%d %H:%M",
    handlers=[RichHandler(rich_tracebacks=True, markup=True), hander])


class Bili_UP:

    def __init__(self, mid: str):

        self.mid = mid
        self.api_user_info = f'http://api.bilibili.com/x/space/acc/info?mid={mid}'
        self.api_video_list = f'http://api.bilibili.com/x/space/arc/search?mid={mid}&ps=30&pn='  # page number
        self.video_url = "https://www.bilibili.com/video/{0}"
        self.user_name = self.get_user_info()['data']['name']

        self.log = logging.getLogger("Bili_UP " + self.user_name)
        self.log.info("[bold green]LOG LOAD SUCCESSFULLY[/]")
        self.log.info(f"[bold blue blink]RUN FOR {self.user_name}[/]")
        self.video_list = []

        self.db = sqlite3.connect('./videos_info.sqlite')
        self.log.info('[bold green]DB CONNECT SUCCESSFULLY[/]')

    def get_user_info(self):
        response = requests.get(self.api_user_info)
        return response.json()

    def get_video_list(self):
        response = requests.get(self.api_video_list)
        self.log.debug(response.json())
        count = response.json()['data']['page']['count']
        for i in range(count // 30 + 1):
            res = requests.get(self.api_video_list + str(i + 1))
            self.log.debug(res.json())
            self.video_list += res.json()['data']['list']['vlist']

        self.log.info(
            f"[bold green]GET {len(self.video_list)} VIDEOS FOR {self.user_name}[/]"
        )
        self.insert_db()

    def insert_db(self):
        cursor = self.db.cursor()
        for item in self.video_list:
            sql = """insert into video_info(aid,bvid,title,author,description,cover_img,is_download) values ('%s','%s','%s','%s','%s','%s','%s');""" % (
                item['aid'], item['bvid'], item['title'], item['author'],
                item['description'], item['pic'], '0')
            try:
                cursor.execute(sql)
                self.db.commit()
                self.log.debug(
                    f"[bold green]INSERT {item['bvid']} SUCCESSFULLY[/]")
            except sqlite3.IntegrityError:
                self.log.info(f"[bold blue]{item['title']} HAS DOWNLOADED[/]")
                self.db.rollback()
            except sqlite3.OperationalError as e:
                self.log.error(f"[bold red]INSERT FAILED[/]")
                self.log.debug(sql)
                self.log.error(e)
                self.db.rollback()
        cursor.close()

    def downloader(self):
        cursor = self.db.cursor()
        sql = """select title,author,bvid from video_info where is_download=0;"""
        cursor.execute(sql)
        data = cursor.fetchall()
        if len(data) == 0:
            self.log.info(f"[bold green]ALL VIDEOS DOWNLOADED[/]")
        all_videos = len(data)
        for row in data:
            video_url = self.video_url.format(row[2])
            self.log.debug(f"video_url -> {video_url}")
            sys.argv = ['you-get', '-o', "./video/" + str(row[1]), video_url]
            you_get.main()
            self.log.info(f"[bold blue]{row[0]} START DOWNLOADING[/]")
            _sql = """update video_info SET is_download=1 where bvid='%s';""" % (
                row[2])
            try:
                cursor.execute(_sql)
                self.db.commit()
            except:
                self.db.rollback()
            self.log.info(f"[bold green]{row[0]} DOWNLOADED[/]")
            self.check_download(all_videos)
        cursor.close()

    def check_download(self, all_videos):
        sql = """select count(*) from video_info where is_download=1;"""
        cursor = self.db.cursor()
        cursor.execute(sql)
        data = cursor.fetchall()
        self.log.info(
            f"[bold green blink]{data[0][0]}/{all_videos} VIDEOS DOWNLOADED[/]"
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
        self.log.info(f"[bold blue]ALL OTHER FILES DELETED[/]")

    def mkdir(self, path: str = "./video"):
        if not os.path.exists(path):
            os.mkdir(path)
            self.log.info(f"[bold green]{path} CREATED[/]")
        else:
            self.log.info(f"[bold blue]{path} EXIST[/]")

    def run(self):
        self.get_video_list()
        self.downloader()
        self.del_files('./video')

    def runx(self):
        # TODO 多线程
        pass
