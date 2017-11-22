#!/usr/bin/env python
#-*- coding: utf-8 -*-
import argparse
import asyncio
import json
import time
import logging
import sys
import traceback
from functools import partial

from aiohttp import web
from aiohttp.web import json_response as aiohttp_json_response, Response
from linux_metrics import (
    disk_busy, disk_reads_writes_persec, disk_usage, cpu_percents,
    load_avg, procs_blocked, procs_running
)


json_dumps = partial(json.dumps, indent=2, sort_keys=True)

logger = logging.getLogger("prometeus_url")

current_app = None
current_loop = asyncio.get_event_loop()


def init_logging():
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(stdout_handler)


def json_error_response(message, status):
    return aiohttp_json_response({
        'status': 'ERROR',
        'error_code': None,
        'msg': message,
        'data': None,
    }, dumps=json_dumps, status=status)


def create_application():
    current_loop.set_debug(True)

    app = web.Application(loop=current_loop, middlewares=[error_middleware])

    app.router.add_get('/metrics', metrics)

    init_logging()

    global current_app
    current_app = app
    logger.info("Start application.")

    return app


async def error_middleware(app, handler):
    async def middleware_handler(request):
        try:
            return await handler(request)
        except web.HTTPException as ex:
            logger.warn(request.url)
            return json_error_response("%s. %s." % (ex, ex.text), ex.status_code)
        except Exception as e:
            logger.exception("Unknown error.")
            return json_error_response("Unknown error. %s %s" % (type(e), traceback.format_exc()), 500)
    return middleware_handler


def _metric(metric_name, val, **labels):
    labels_str = ''
    if labels:
        labels_list = []
        for name, l_val in labels.items():
            labels_list.append('%s="%s"' % (name, l_val))
        labels_str = "{" + ','.join(labels_list) + "}"

    return "%s%s %s %s000" % (metric_name, labels_str, val, int(time.time()))


async def metrics(request):
    global counter

    data = [
        _metric("disc_busy", disk_busy("sda"), dev="sda"),
        _metric("load_average", load_avg()[0]),
        _metric("procs_blocked", procs_blocked()),
        _metric("procs_running", procs_running()),
        _metric("cpu", 100 - cpu_percents()["idle"]),
        #  list(map(lambda x: x/1024/1024/1024, mem_stats())),

        #  net_stats_ifconfig(),
        #  rx_tx_bits(),
        #  rx_tx_bytes(),
        #  rx_tx_dump(),
    ]

    #  reads, writes = disk_reads_writes("sda")
    #  data.append(_metric("disc_sum", reads, dev="sda", operation="reads"))
    #  data.append(_metric("disc_sum", writes, dev="sda", operation="writes"))

    reads, writes = disk_reads_writes_persec("sda")
    data.append(_metric("disc_persec", reads, dev="sda", operation="reads"))
    data.append(_metric("disc_persec", writes, dev="sda", operation="writes"))

    disc_path = "/dev/mapper/mint--vg-root"
    disc = disk_usage(disc_path)
    data.append(_metric("disc_space", disc[1]/1024/1024, dev=disc_path, type="size"))
    data.append(_metric("disc_space", disc[2]/1024/1024, dev=disc_path, type="used"))
    data.append(_metric("disc_space", disc[3]/1024/1024, dev=disc_path, type="free"))

    data = "\n".join(data)

    return Response(text=data, status=200, content_type="text/plain")


parser = argparse.ArgumentParser(description="PrometeusUrl")
parser.add_argument('--host', default="127.0.0.1")
parser.add_argument('--port', type=int, default=8080)

args = parser.parse_args()

app = create_application()

web.run_app(app, port=args.port, host=args.host)
