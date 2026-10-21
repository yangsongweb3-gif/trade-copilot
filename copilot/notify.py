"""发通知：按级别决定发到哪。

- urgent：控制台 + QQ 私聊 + PushPlus
- important：控制台 + QQ 私聊
- info：只打控制台

只发私聊，从不发群：提醒里有计划和价位，属于个人信息。
"""
import logging
from datetime import datetime

import requests

from .rules import IMPORTANT, URGENT, Signal

log = logging.getLogger(__name__)
ICON = {URGENT: '🔴', IMPORTANT: '🟡'}


def format_signal(s: Signal) -> str:
    return f"{ICON.get(s.level, '🟢')} {s.title}\n{s.text}\n时间：{datetime.now():%Y-%m-%d %H:%M}\n（系统只提醒，不下单）"


class Notifier:
    def __init__(self, env: dict, dry_run: bool = False):
        self.env, self.dry_run = env, dry_run

    def send(self, s: Signal) -> None:
        text = format_signal(s)
        print(text + '\n')
        if self.dry_run or s.level not in (URGENT, IMPORTANT):
            return
        self._qq_private(text)
        if s.level == URGENT:
            self._pushplus(s.title, text)

    def send_report(self, text: str) -> None:
        """整段报告（如今日环境灯）：打印，并发 QQ 私聊。"""
        print(text + '\n')
        if not self.dry_run:
            self._qq_private(text)

    def _qq_private(self, text: str) -> None:
        url, user = self.env.get('NAPCAT_URL', '').rstrip('/'), self.env.get('QQ_USER_ID', '')
        if not url or not user.isdigit():
            log.warning('没配 NAPCAT_URL / QQ_USER_ID，QQ 提醒跳过')
            return
        headers = {'Authorization': 'Bearer ' + self.env['NAPCAT_TOKEN']} if self.env.get('NAPCAT_TOKEN') else {}
        try:
            # NapCat 在本机，不走代理
            r = requests.post(f'{url}/send_private_msg', headers=headers, timeout=10,
                              proxies={'http': None, 'https': None},
                              json={'user_id': int(user), 'message': [{'type': 'text', 'data': {'text': text}}]})
            ok = r.json().get('retcode') == 0
            log.info('QQ 私聊%s', '已发送' if ok else f'发送失败：{r.text[:200]}')
        except Exception as e:  # 通知失败不能让主循环崩
            log.warning('QQ 私聊发送异常：%s', e)

    def _pushplus(self, title: str, text: str) -> None:
        token = self.env.get('PUSHPLUS_TOKEN', '')
        if not token:
            return
        try:
            r = requests.post('https://www.pushplus.plus/send', timeout=10,
                              json={'token': token, 'title': title, 'content': text.replace('\n', '<br>'), 'template': 'html'})
            log.info('PushPlus：%s', r.json().get('msg'))
        except Exception as e:
            log.warning('PushPlus 发送异常：%s', e)
