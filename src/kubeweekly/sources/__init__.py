from __future__ import annotations

from kubeweekly.config import SourcesConfig
from kubeweekly.sources.artifacthub import ArtifactHubSource
from kubeweekly.sources.base import Source
from kubeweekly.sources.cloud_providers import CloudProviderSource
from kubeweekly.sources.cve import CveSource
from kubeweekly.sources.github import GitHubSource
from kubeweekly.sources.hackernews import HackerNewsSource
from kubeweekly.sources.mailing_lists import MailingListSource
from kubeweekly.sources.reddit import RedditSource
from kubeweekly.sources.rss import RssSource


def build_sources(config: SourcesConfig, github_token: str | None = None) -> list[Source]:
    sources: list[Source] = []

    if config.rss:
        sources.append(RssSource(config.rss))

    if config.github.get("releases") or config.github.get("topic_search"):
        sources.append(
            GitHubSource(
                releases=config.github.get("releases", []),
                topic_search=config.github.get("topic_search", {}),
                token=github_token,
            )
        )

    if config.artifacthub.get("enabled"):
        sources.append(ArtifactHubSource(kinds=config.artifacthub.get("kinds", [])))

    if config.hackernews.get("enabled"):
        sources.append(HackerNewsSource(queries=config.hackernews.get("queries", [])))

    if config.reddit.get("enabled"):
        sources.append(RedditSource(subreddits=config.reddit.get("subreddits", [])))

    if config.cve.get("enabled"):
        sources.append(CveSource(keywords=config.cve.get("keywords", [])))

    if config.cloud_providers:
        sources.append(CloudProviderSource(config.cloud_providers))

    if config.mailing_lists:
        sources.append(MailingListSource(config.mailing_lists))

    return sources
