"""Recovered filename import records without an extra runtime dependency."""

from dataclasses import dataclass, field, asdict


@dataclass
class ScoreAsset:
    source_path: str
    file_name: str
    extension: str
    detected_title: str
    confidence: int
    detected_key: str | None = None

    def __post_init__(self):
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be 0~100")


@dataclass
class SongRecord:
    wgid: str
    title: str
    confidence: int
    available_keys: list[str] = field(default_factory=list)
    assets: list[ScoreAsset] = field(default_factory=list)
    status: str = "AI 초안"
    review_status: str = "미검수"
    user_editable: bool = True

    @property
    def representative_key(self):
        return self.available_keys[0] if self.available_keys else None

    def model_dump(self):
        return asdict(self)

    def csv_row(self):
        return {
            "WGID": self.wgid,
            "곡명": self.title,
            "대표 Key": self.representative_key,
            "사용 가능 Key": ", ".join(self.available_keys),
            "악보 파일 수": len(self.assets),
            "악보 파일": " | ".join(a.file_name for a in self.assets),
            "AI 상태": self.status,
            "검수 상태": self.review_status,
            "AI 신뢰도": self.confidence,
            "사용자 수정 허용": self.user_editable,
        }
