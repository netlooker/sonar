"""Robots.txt policy enforcement."""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from sonar.errors import SonarForbiddenError, SonarRobotsUnavailableError


def assert_allowed_by_robots(client: httpx.Client, url: str, user_agent: str) -> None:
    parts = urlsplit(url)
    robots_url = urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")
    try:
        response = client.get(robots_url)
    except httpx.HTTPError as exc:
        raise SonarRobotsUnavailableError("robots.txt request failed.") from exc

    if response.status_code == 404:
        return
    if response.status_code in {401, 403}:
        raise SonarForbiddenError("robots.txt disallows access to this site.")
    if response.status_code < 200 or response.status_code >= 300:
        raise SonarRobotsUnavailableError("robots.txt request failed.")

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(user_agent, url):
        raise SonarForbiddenError("robots.txt disallows access to this URL.")
