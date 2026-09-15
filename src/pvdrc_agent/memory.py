class InMemoryEpisodeStore:
    def __init__(self) -> None:
        self.episodes: list[dict[str, object]] = []

    def record(self, episode: dict[str, object]) -> None:
        self.episodes.append(dict(episode))
