# log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request" '
#                     '$status $body_bytes_sent "$http_referer" '
#                     '"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" '
#                     '$request_time';

import gzip
import json
import os
import re
import shutil
import sys
from argparse import ArgumentParser
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path
from typing import Generator

import structlog

logger = structlog.get_logger()


config: dict[str, str] = {
    "REPORT_SIZE": "1000",
    "REPORT_DIR": "./reports",
    "LOG_DIR": "./log",
    "REGISTRY_FILE": ".processed.txt",
}

LogEntry = namedtuple(
    "LogEntry",
    [
        "remote_addr",
        "remote_user",
        "http_x_real_ip",
        "time_local",
        "request",
        "status",
        "body_bytes_sent",
        "http_referer",
        "http_user_agent",
        "http_x_forwarded_for",
        "http_X_REQUEST_ID",
        "http_X_RB_USER",
        "request_time",
    ],
)

LogFile = namedtuple("LogFile", "file date")


def parse_config(file_path: str, default: dict[str, str]) -> dict | None:
    """
    Read and parse config file. Use default params from default config if them skipped in user config

    :param file_path: path to user config file
    :param default: default config as dict
    :return: dict config or None in case of errors
    """
    try:
        logger.info("Try readind config file %s", file_path)

        with open(file_path, "rt", encoding="utf8") as config_file:
            lines = config_file.readlines()
            user_config: dict[str, str | int] = dict()

            for line in lines:
                param_value = line.split("=")

                if len(param_value) < 2:
                    logger.error("Wrong format for line %s", line)
                    return None

                user_config[param_value[0].strip()] = param_value[1].strip()

            for param, value in default.items():
                if not user_config.get(param):
                    user_config[param] = value

            logger.info("Config file was successfully  read")

            return user_config
    except FileNotFoundError:
        logger.error("Can't read config file %s", file_path)
        return None


def get_last_log_file(log_dir: str, registry_file: str) -> LogFile | None:
    """
    Return name of last log file base on date in file name
    : log_dir: directory where to search log files
    : registry_file: file where processed log file names are stored
    : return:  LogFile | None. None in case of error
    """
    processed_logs = []
    if os.path.exists(registry_file):
        with open(registry_file, mode="rt", encoding="utf-8") as reg_file:
            processed_logs = [line.strip() for line in reg_file.readlines()]

    log_file_pttn = re.compile("^nginx-access-ui.log-[\d]{8}(.gz)*$")
    log_files = [
        f.name
        for f in Path(log_dir).iterdir()
        if not f.is_dir() and log_file_pttn.match(f.name)
    ]

    date_pattern = re.compile("\d{8}")
    # max_date = datetime.strptime("19700101", "%Y%m%d")
    max_date = datetime.min

    last_log_file = None

    for log_file in log_files:
        if log_file in processed_logs:
            logger.debug("Log file %s had already been processed", log_file)
            continue

        log_date = log_file.replace(".gz", "")[-8:]
        if date_pattern.match(log_date):
            log_date_d = datetime.strptime(log_date, "%Y%m%d")
            if log_date_d > max_date:
                max_date = log_date_d
                last_log_file = log_file
        else:
            logger.error(
                "Invalid date format in log file name %s. Expected date like yyyymmdd at the end of name",
                log_file,
            )
            return None

    if not last_log_file:
        logger.error(
            "Logs file not found. Expected .gz files or files with no extension \
                     with name like 'nginx-access-ui.log-yyyymmdd"
        )
        return None

    logger.info(
        "Found last log file %s to process in log dir %s", last_log_file, log_dir
    )

    return LogFile(file=os.path.join(log_dir, last_log_file), date=max_date)


def log_parser(log_file) -> Generator[LogEntry, None, None]:
    """
    Parse log line in log_file. Returns namedtuple LogEntry
    """

    is_gzipped = log_file.endswith(".gz")
    open_func = gzip.open if is_gzipped else open

    with open_func(log_file, "rt", encoding="utf-8") as f:
        while log_line := f.readline():
            parts = [p for p in log_line.split(" ") if p != ""]

            log_values = []
            multiword_value: list[str] = []

            for part in parts:
                if (
                    (part.find('"') < 0 or part.count('"') == 2)
                    and part.find("[") != 0
                    and part.find("]") != len(part) - 1
                ):
                    if len(multiword_value) > 0:
                        multiword_value.append(part)
                    else:
                        log_values.append(part.strip())
                elif part.find('"') == 0 or part.find("[") == 0:
                    multiword_value.append(part)
                elif part.find('"') > 0 or part.find("]") > 0:
                    multiword_value.append(part)
                    log_values.append(" ".join(multiword_value))
                    multiword_value = []

            yield LogEntry(
                remote_addr=log_values[0],
                remote_user=log_values[1],
                http_x_real_ip=log_values[2],
                time_local=log_values[3],
                request=log_values[4],
                status=log_values[5],
                body_bytes_sent=log_values[6],
                http_referer=log_values[7],
                http_user_agent=log_values[8],
                http_x_forwarded_for=log_values[9],
                http_X_REQUEST_ID=log_values[10],
                http_X_RB_USER=log_values[11],
                request_time=log_values[12],
            )


def mediana(values: list[float]) -> float:
    """
    Return mediane value of values list
    """
    if not values:
        return 0

    s_values = sorted(values)
    return s_values[int(len(s_values) / 2)]


def _copy_report_resources(report_dir: str, resources: list[str]):
    """
    Copy resources necessary for reports. Ex.: js lib files
    :report_dir: directory with generated repors where resources files will be copied
    :resources: list of files in 'resources' directory
    """
    for resource in resources:
        resource_file = os.path.join("resources/", resource)
        target_file = os.path.join(report_dir, os.path.basename(resource))
        if not os.path.exists(resource_file):
            shutil.copy(resource_file, target_file)
            logger.info("Copied resource file %s into %s", resource_file, target_file)


def write_report(
    log_parser: Generator[LogEntry, None, None],
    log_date: datetime,
    report_dir: str,
    report_size: int,
):
    """
    Parse log file with log_parser and generate html report which is placed into report_dir
    """
    total_counters = {"count": 0, "time_sum": 0.0}
    url_counters: dict[str, dict[str, int | float]] = dict()
    url_req_times: dict[str, list[float]] = dict()

    logger.info("Start parsing log")

    for log_line in log_parser:
        if len(log_line.request) == 3:
            continue

        _, url = log_line.request.split(" ")[:2]
        if not url_counters.get(url):
            url_counters[url] = {"count": 0, "time_sum": 0, "time_max": 0}
            url_req_times[url] = []

        url_counters[url]["count"] += 1
        url_counters[url]["time_sum"] += float(log_line.request_time)
        url_req_times[url].append(float(log_line.request_time))

        if url_counters[url]["time_max"] < float(log_line.request_time):
            url_counters[url]["time_max"] = float(log_line.request_time)

        total_counters["count"] += 1
        total_counters["time_sum"] += float(log_line.request_time)

    logger.info("Log file was parsed. Start generating report")

    table_data = []

    for url, counters in url_counters.items():
        table_data.append(
            {
                "url": url,
                "count": counters["count"],
                "count_perc": round(
                    counters["count"] / total_counters["count"] * 100, 3
                ),
                "time_avg": round(counters["time_sum"] / counters["count"], 3),
                "time_max": counters["time_max"],
                "time_med": mediana(url_req_times[url]),
                "time_perc": round(
                    counters["time_sum"] / total_counters["time_sum"] * 100, 3
                ),
                "time_sum": round(counters["time_sum"], 3),
            }
        )

    report_file_name = f'report-{log_date.strftime("%Y.%m.%d")}.html'
    report_full_path = os.path.join(report_dir, report_file_name)

    with open(
        "./resources/templates/report.html", "r", encoding="utf-8"
    ) as template_file:
        from string import Template

        template = Template(template_file.read())
        html_content = template.safe_substitute(table_json=json.dumps(table_data))

    with open(report_full_path, "w", encoding="utf-8") as report_file:
        report_file.write(html_content)

    _copy_report_resources(report_dir, ["js/jquery.tablesorter.min.js"])

    logger.info("Created report %s", report_file_name)


def mark_as_processed(log_file: str, registry_file: str):
    with open(registry_file, mode="a+", encoding="utf-8") as file:
        file.write("\n")
        file.write(os.path.basename(log_file))


def main(args):
    user_config = parse_config(args.config, default=config)

    if not user_config:
        sys.exit(
            f"Error: can't read config file {args.config}. Please check path and format"
        )

    registry_file = os.path.join(user_config["LOG_DIR"], user_config["REGISTRY_FILE"])

    last_log_file = get_last_log_file(user_config["LOG_DIR"], registry_file)

    if not last_log_file:
        logger.info(
            "No log files was found in %s for processing", user_config["LOG_DIR"]
        )
        sys.exit(0)

    log_parser_gen = log_parser(last_log_file.file)

    write_report(
        log_parser_gen,
        last_log_file.date,
        user_config["REPORT_DIR"],
        user_config["REPORT_SIZE"],
    )

    mark_as_processed(last_log_file.file, registry_file)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        default="./config",
        help="Path to config file. Default is ./config. Format: list of rows key=value",
    )

    args = parser.parse_args()

    main(args)
