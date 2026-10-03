from dataclasses import dataclass

@dataclass
class RepositoryContext:
    provider: str        # "github"
    owner: str
    name: str
    full_name: str       # "owner/repo"
    url: str
    default_branch: str
    visibility: str      # "public" | "private"
