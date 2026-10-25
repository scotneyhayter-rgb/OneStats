"""Generic XML adapter — Phase 8, Stage 8.4.

Imports a structured XML document of ``<match>`` elements (fields as attributes and/or child element
text), handing the rows to the shared tabular builder. Parsing uses ``defusedxml`` because import
files are untrusted — external entities, DTDs and entity-expansion (billion-laughs) attacks are
rejected. Blank fields are unknown; nothing is invented.
"""
from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from onestats.domain.importing.adapter import SourceAdapter, register_adapter
from onestats.domain.importing.model import CanonicalDataset
from onestats.domain.importing.tabular import build_match_summary


class XmlGenericAdapter(SourceAdapter):
    format_id = "generic_xml"
    display_name = "XML match list"
    capabilities = frozenset({"matches"})

    def detect(self, sample: bytes | str, filename: str | None = None) -> float:
        text = sample.decode("utf-8-sig", errors="ignore") if isinstance(sample, bytes) else sample
        head = text.lstrip()[:2000].lower()
        if not head.startswith("<"):
            return 0.0
        score = 0.3
        if "<match" in head:
            score += 0.4
        for marker in ("hometeam", "awayteam", "<matches", "<result"):
            if marker in head:
                score += 0.1
        return min(score, 0.9)

    def parse(self, content: bytes | str, *, filename: str | None = None) -> list[dict[str, Any]]:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        try:
            root = fromstring(content)
        except DefusedXmlException as exc:
            raise ValueError(f"generic_xml: unsafe XML rejected ({exc})") from exc
        except ParseError as exc:
            raise ValueError(f"generic_xml: malformed XML ({exc})") from exc
        # match elements anywhere: <match> directly, or under a wrapper like <matches>
        matches = root.iter("match") if root.tag != "match" else [root]
        out: list[dict[str, Any]] = []
        for el in matches:
            row: dict[str, Any] = dict(el.attrib)           # attributes first
            for child in el:                                 # child element text overrides/extends
                if child.text is not None and child.text.strip():
                    row[child.tag] = child.text.strip()
            if row:
                out.append(row)
        return out

    def normalize(self, raw: list[dict[str, Any]], *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        return build_match_summary(raw, source_system=self.format_id, overrides=mapping)


register_adapter(XmlGenericAdapter())
