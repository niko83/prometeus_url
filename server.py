#!/usr/bin/env python
#-*- coding: utf-8 -*-
import os
import asyncio
import json
import time
import logging
import sys
import traceback
from functools import partial
import aiohttp

from aiohttp import web
from aiohttp.web import json_response as aiohttp_json_response, Response
from linux_metrics import (
    disk_busy, disk_usage, cpu_percents,
    load_avg, procs_blocked, procs_running, rx_tx_bytes,
    disk_reads_writes,
)
import settings


def mem_stats():
    mem = {}

    with open('/proc/meminfo') as f:
        for line in f:
            if line.startswith('MemTotal:'):
                mem['total'] = int(line.split()[1]) * 1024
            elif line.startswith('Active: '):
                mem['active'] = int(line.split()[1]) * 1024
            elif line.startswith('MemFree:'):
                mem['free'] = (int(line.split()[1]) * 1024)
            elif line.startswith('Cached:'):
                mem['cached'] = (int(line.split()[1]) * 1024)
            elif line.startswith('Buffers: '):
                mem['buffers'] = (int(line.split()[1]) * 1024)
            elif line.startswith('SwapTotal: '):
                mem['swap_total'] = (int(line.split()[1]) * 1024)
            elif line.startswith('SwapFree: '):
                mem['swap_free'] = (int(line.split()[1]) * 1024)

    used = mem['total'] - mem['free'] - mem['cached'] - mem['buffers']
    cached = mem['cached']
    buffers = mem['buffers']
    free = mem['free']

    return (used, cached, buffers, free)


json_dumps = partial(json.dumps, indent=2, sort_keys=True)

logger = logging.getLogger("prometheus_url")

current_app = None
current_loop = asyncio.get_event_loop()


def init_logging():

    logger = logging.getLogger("prometheus_url")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [PID:{0}] [%(name)s.%(funcName)s]: %(message)s".format(os.getpid())
    ))
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [PID:{0}] [%(name)s.%(funcName)s]: %(message)s".format(os.getpid())
    ))
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)


def json_error_response(message, status):
    return aiohttp_json_response({
        'status': 'ERROR',
        'error_code': None,
        'msg': message,
        'data': None,
    }, dumps=json_dumps, status=status)


def create_application():
    if settings.DEBUG:
        current_loop.set_debug(True)

    init_logging()

    app = web.Application(loop=current_loop, middlewares=[error_middleware])

    app.router.add_get('/metrics', metrics)

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

    logger.info(request)

    data = [
        _metric("load_average", load_avg()[0]),
        _metric("procs_blocked", procs_blocked()),
        _metric("procs_running", procs_running()),
        _metric("cpu", 100 - cpu_percents()["idle"]),
    ]

    for interface in settings.NETWORK_INTERFACES:
        rx_tx = list(map(lambda x: x/1024/1024, rx_tx_bytes(interface)))
        data.append(_metric("network", rx_tx[0], type="rx", interface=interface))
        data.append(_metric("network", rx_tx[1], type="tx", interface=interface))

    for dev in settings.DISKS:
        data.append(_metric("disk_busy", disk_busy(dev), dev=dev))

        reads, writes = disk_reads_writes(dev)
        data.append(_metric("disk_sum", reads, dev=dev, operation="reads"))
        data.append(_metric("disk_sum", writes, dev=dev, operation="writes"))

        disk = disk_usage("/dev/" + dev)
        data.append(_metric("disk_space", disk[1]/1024/1024, dev=dev, type="size"))
        data.append(_metric("disk_space", disk[2]/1024/1024, dev=dev, type="used"))
        data.append(_metric("disk_space", disk[3]/1024/1024, dev=dev, type="free"))

    ram = list(map(lambda x: x/1024/1024/1024, mem_stats()))

    data.append(_metric("ram", ram[0], type="used"))
    data.append(_metric("ram", ram[1], type="cached"))
    data.append(_metric("ram", ram[2], type="buffers"))
    data.append(_metric("ram", ram[3], type="free"))

    data = "\n".join(data)

    return Response(text=data, status=200, content_type="text/plain")


app = create_application()

web.run_app(app, port=settings.PORT, host=settings.HOST)
