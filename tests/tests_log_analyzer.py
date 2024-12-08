import json
import os
from datetime import datetime
from unittest.mock import mock_open, patch

from log_analyzer.log_analyzer import (
    LogEntry,
    get_last_log_file,
    parse_config,
    write_report,
)

default_config = {
    "LOG_DIR": "some_dir_1",
    "REPORT_DIR": "some_dir_2",
}


def test_parse_config_success():
    config_data = "LOG_DIR=user_dir_1\nREPORT_SIZE=100\n"

    with patch("builtins.open", mock_open(read_data=config_data)):
        result = parse_config("user_config_file_path", default_config)

    assert result == {
        "LOG_DIR": "user_dir_1",
        "REPORT_SIZE": "100",
        "REPORT_DIR": "some_dir_2",
    }


def test_parse_config_invalid_format():
    config_data = "LOG_DIR=user_dir_1\ninvalid_line\nREPORT_SIZE=100\n"

    with patch("builtins.open", mock_open(read_data=config_data)):
        result = parse_config("user_config_file_path", default_config)

    assert result is None


def test_parse_config_file_not_found():
    with patch("builtins.open", side_effect=FileNotFoundError):
        result = parse_config("dummyuser_config_file_path_path", default_config)

    assert result is None


def test_get_last_log_file_found():
    log_dir = "mock_log_dir"
    registry_file = "processed.txt"

    log_files = [
        "nginx-access-ui.log-20230301",
        "nginx-access-ui.log-20230302.gz",
        "nginx-access-ui.log-20230303.gz",
    ]

    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data="nginx-access-ui.log-20230301\n")
    ), patch("pathlib.Path.iterdir") as mock_iterdir:

        # Mock the Path.iterdir to return our fake log files
        mock_iterdir.return_value = [
            patch("pathlib.PosixPath") for filename in log_files
        ]
        for path, filename in zip(mock_iterdir.return_value, log_files):
            path.name = filename
            path.is_dir = lambda: False

        last_log_file = get_last_log_file(log_dir, registry_file)

    assert last_log_file
    assert last_log_file.file == os.path.join(
        log_dir, "nginx-access-ui.log-20230303.gz"
    )
    assert last_log_file.date == datetime.strptime("20230303", "%Y%m%d")


def test_get_last_log_file_no_log_files():
    log_dir = "mock_log_dir"
    registry_file = "processed.txt"

    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data="")
    ), patch("pathlib.Path.iterdir") as mock_iterdir:

        # Mock the Path.iterdir to return no log files
        mock_iterdir.return_value = []

        last_log_file = get_last_log_file(log_dir, registry_file)

    assert last_log_file is None


def test_write_report():
    log_date = datetime(2023, 3, 1)
    report_dir = "mock_report_dir"
    log_parser = (
        LogEntry(
            remote_addr="",
            remote_user="",
            http_x_real_ip="",
            time_local="",
            request="GET /page1 0.1",
            status="200 OK",
            body_bytes_sent=100500,
            http_referer="",
            http_user_agent="",
            http_x_forwarded_for="",
            http_X_REQUEST_ID="",
            http_X_RB_USER="",
            request_time=0.1,
        ),
        LogEntry(
            remote_addr="",
            remote_user="",
            http_x_real_ip="",
            time_local="",
            request="GET /page1 0.2",
            status="200 OK",
            body_bytes_sent=100500,
            http_referer="",
            http_user_agent="",
            http_x_forwarded_for="",
            http_X_REQUEST_ID="",
            http_X_RB_USER="",
            request_time=0.2,
        ),
        LogEntry(
            remote_addr="",
            remote_user="",
            http_x_real_ip="",
            time_local="",
            request="GET /page2 0.3",
            status="200 OK",
            body_bytes_sent=100500,
            http_referer="",
            http_user_agent="",
            http_x_forwarded_for="",
            http_X_REQUEST_ID="",
            http_X_RB_USER="",
            request_time=0.3,
        ),
        LogEntry(
            remote_addr="",
            remote_user="",
            http_x_real_ip="",
            time_local="",
            request="GET /page3 0.4",
            status="200 OK",
            body_bytes_sent=100500,
            http_referer="",
            http_user_agent="",
            http_x_forwarded_for="",
            http_X_REQUEST_ID="",
            http_X_RB_USER="",
            request_time=0.4,
        ),
    )

    with patch("builtins.open", mock_open(read_data="table=$table_json")) as _mock_open:
        write_report(log_parser, log_date, report_dir, report_size=100)

        # Check template was read
        _mock_open.assert_any_call(
            "./resources/templates/report.html", "r", encoding="utf-8"
        )

        # Check report was read
        report_file_name = f'report-{log_date.strftime("%Y.%m.%d")}.html'
        report_full_path = os.path.join(report_dir, report_file_name)
        _mock_open.assert_any_call(report_full_path, "w", encoding="utf-8")

        # Check report content
        expected_table_data = [
            {
                "url": "/page1",
                "count": 2,
                "count_perc": 50.0,
                "time_avg": 0.15,
                "time_max": 0.2,
                "time_med": 0.2,
                "time_perc": 30.0,
                "time_sum": 0.3,
            },
            {
                "url": "/page2",
                "count": 1,
                "count_perc": 25.0,
                "time_avg": 0.3,
                "time_max": 0.3,
                "time_med": 0.3,
                "time_perc": 30.0,
                "time_sum": 0.3,
            },
            {
                "url": "/page3",
                "count": 1,
                "count_perc": 25.0,
                "time_avg": 0.4,
                "time_max": 0.4,
                "time_med": 0.4,
                "time_perc": 40.0,
                "time_sum": 0.4,
            },
        ]

        expected_json = json.dumps(expected_table_data)
        _mock_open().write.assert_called_once_with(f"table={expected_json}")
