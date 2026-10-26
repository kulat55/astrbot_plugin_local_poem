# -*- coding: utf-8 -*-
"""本地古诗插件：/诗接 对句、/诗考 出题、/诗答 判定。
数据来自 chinese-poetry 数据集（水墨唐诗/唐诗三百首/千家诗），已转简体随包分发。
"""
import json
import os
import random
import re

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

_PUNCT = " \t\n\r，。、；：！？·“”‘’《》〈〉〔〕（）()[]【】\"'‘’—…～-"


def _norm(s: str) -> str:
    return re.sub(r"[\s%s]" % re.escape(_PUNCT), "", s or "")


class LocalPoemPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        _data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "poems.json")
        with open(_data, encoding="utf-8") as _f:
            db = json.load(_f)
        self.couples = db.get("couples", [])
        self.meta = db.get("meta", {})
        # 上句/下句 -> 对句 索引
        self.by_up = {}
        self.by_down = {}
        for c in self.couples:
            self.by_up.setdefault(_norm(c["up"]), []).append(c)
            self.by_down.setdefault(_norm(c["down"]), []).append(c)
        self.quiz = {}  # session_id -> {up, down, title, author}

    # ---------- /诗接：给上句接出下句，或给下句反推出上句 ----------
    @filter.command("诗接")
    async def poem_join(self, event, text: GreedyStr):
        line = _norm(str(text))
        if not line:
            yield event.plain_result("给我一句诗嘛，比如 /诗接 床前明月光")
            return
        hit = self.by_up.get(line) or self.by_down.get(line)
        if not hit:
            yield event.plain_result("这句不在我的小诗库里，换一句试试？")
            return
        c = hit[0]
        if line == _norm(c["up"]):
            out = f"「{c['down']}」\n—— {c['author']}《{c['title']}》"
        else:
            out = f"「{c['up']}」\n—— {c['author']}《{c['title']}》"
        yield event.plain_result(out)

    # ---------- /诗考：随机出一联，出上句考下句 ----------
    @filter.command("诗考")
    async def poem_quiz(self, event):
        if not self.couples:
            yield event.plain_result("诗库是空的，没法考。")
            return
        c = random.choice(self.couples)
        self.quiz[event.message_obj.session_id] = c
        yield event.plain_result(
            f"考你一句：\n「{c['up']}」\n\n接下一句，回 /诗答 <你的答案>"
        )

    # ---------- /诗答：判定 ----------
    @filter.command("诗答")
    async def poem_answer(self, event, text: GreedyStr):
        c = self.quiz.get(event.message_obj.session_id)
        if not c:
            yield event.plain_result("我还没出题呢，先 /诗考 一下。")
            return
        ans = _norm(str(text))
        expect = _norm(c["down"])
        ok = bool(ans) and (ans == expect or expect in ans)
        full = f"{c['up']}，{c['down']}"
        if ok:
            yield event.plain_result(
                f"答对啦！\n「{full}」\n—— {c['author']}《{c['title']}》"
            )
        else:
            yield event.plain_result(
                f"不对哦，答案是「{c['down']}」。\n「{full}」\n—— {c['author']}《{c['title']}》"
            )
        self.quiz.pop(event.message_obj.session_id, None)
