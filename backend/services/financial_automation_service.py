"""Programmatic financial automation runners for Flow steps."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import FinancialAutomationRecord, FinancialUtilityBill, ScheduledEvent
from services.password_vault_service import PasswordVaultError, PasswordVaultService, get_password_vault_encryptor

logger = logging.getLogger(__name__)


class FinancialAutomationError(RuntimeError):
    """Raised for user-actionable financial automation failures."""


def _parse_brl_cents(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9,.-]", "", value)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "." in cleaned:
        integer, _, fraction = cleaned.rpartition(".")
        cleaned = f"{integer}.{fraction}" if len(fraction) == 2 else cleaned.replace(".", "")
    try:
        return int((Decimal(cleaned) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def _format_brl(amount_cents: Optional[int]) -> Optional[str]:
    if amount_cents is None:
        return None
    value = Decimal(amount_cents) / Decimal(100)
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _reference_month_from_due_date(due_date: Optional[str]) -> Optional[str]:
    if not due_date:
        return None
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", due_date)
    if not match:
        return None
    return f"{match.group(2)}/{match.group(3)}"


def _to_br_date(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return f"{iso.group(3)}/{iso.group(2)}/{iso.group(1)}"
    br = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw)
    return f"{br.group(1)}/{br.group(2)}/{br.group(3)}" if br else ""


def _to_reference_month(value: Optional[str], fallback_date: Optional[str] = None) -> str:
    raw = str(value or "").strip()
    iso_month = re.match(r"^(\d{4})-(\d{2})$", raw)
    if iso_month:
        return f"{iso_month.group(2)}/{iso_month.group(1)}"
    month = re.match(r"^(\d{2})/(\d{4})$", raw)
    if month:
        return f"{month.group(1)}/{month.group(2)}"
    return (
        _reference_month_from_due_date(raw)
        or _reference_month_from_due_date(fallback_date)
        or ""
    )


def _to_iso_date(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    br = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    return f"{br.group(3)}-{br.group(2)}-{br.group(1)}" if br else ""


def _reference_month_yyyy_mm(value: Optional[str], fallback_date: Optional[str] = None) -> str:
    raw = str(value or "").strip()
    match = re.match(r"^(\d{2})/(\d{4})$", raw)
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    iso = _to_iso_date(raw) or _to_iso_date(fallback_date)
    return iso[:7] if iso else ""


def _digits_only(value: Optional[str]) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _barcode_preview(barcode: Optional[str]) -> Optional[str]:
    if not barcode:
        return None
    digits = re.sub(r"\D", "", barcode)
    if len(digits) < 8:
        return "[REDACTED]"
    return f"[REDACTED:{len(digits)}:{digits[-4:]}]"


def _is_paid_status(status: Optional[str]) -> bool:
    normalized = (status or "").strip().lower()
    return any(marker in normalized for marker in ("pago", "paid", "quitad", "liquidad", "baixad"))


_SENSITIVE_PAYLOAD_KEYS = {
    "authorization",
    "barcode",
    "cartao",
    "codigo_barras",
    "cvv",
    "linha_digitavel",
    "otp",
    "password",
    "senha",
    "secret",
    "token",
    "totp",
    "value",
}


def _redact_financial_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted: Dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(marker in normalized_key for marker in _SENSITIVE_PAYLOAD_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_financial_payload(value)
        return redacted
    if isinstance(payload, list):
        return [_redact_financial_payload(item) for item in payload]
    if isinstance(payload, str):
        digits = re.sub(r"\D", "", payload)
        if len(digits) >= 24:
            return f"[REDACTED:{len(digits)}:{digits[-4:]}]"
        if payload.strip().lower().startswith("op://"):
            return "[REDACTED]"
    return payload


class FinancialAutomationService:
    """Tenant-scoped storage primitives for financial records (utility bills, etc).

    Provider-identity constants stay so that visible Data Transform parsers
    (`_parse_consigaz_bill`, `_parse_medsenior_bill`) can label rows with a stable
    automation/provider key when no upstream config supplies one.
    """

    MODERNA_AUTOMATION_ID = "cond_sao_blas_204_boleto_condominio"
    MODERNA_PROVIDER = "moderna"
    CONSIGAZ_AUTOMATION_ID = "consigaz_gas_cond_sao_blas_204"
    CONSIGAZ_PROVIDER = "consigaz"
    CONSIGAZ_ISSUER = "Consigaz - Distribuidora de Gas Ltda - Barueri"
    MEDSENIOR_AUTOMATION_ID = "medsenior_samedil_plano_saude_mae"
    MEDSENIOR_PROVIDER = "medsenior"
    MEDSENIOR_ISSUER = "Medsenior / Samedil"

    def __init__(self, db: Session, *, tenant_id: str) -> None:
        if not tenant_id:
            raise FinancialAutomationError("tenant_id_required")
        self.db = db
        self.tenant_id = tenant_id

    def _build_bill_store_output(
        self,
        record_result: Dict[str, Any],
        extracted: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return storage/dedupe output without creating hidden notifications."""
        record: FinancialUtilityBill = record_result["record"]
        condition_met = bool(
            (record_result["created"] or record_result["barcode_changed"])
            and record.barcode_preview
            and not _is_paid_status(record.status)
        )
        return {
            "status": "completed",
            "success": True,
            "record_kind": "utility_bill",
            "automation_key": record.automation_key,
            "provider": record.provider,
            "unit_id": record.unit_id,
            "asset": record.asset,
            "reference_month": record.reference_month,
            "due_date": record.due_date,
            "amount_cents": record.amount_cents,
            "amount_display": _format_brl(record.amount_cents),
            "bill_status": record.status,
            "barcode_detected": bool(extracted.get("barcode")),
            "barcode_preview": record.barcode_preview,
            "redacted": True,
            "dedupe": {
                "created": record_result["created"],
                "updated": record_result["updated"],
                "barcode_changed": record_result["barcode_changed"],
                "dedupe_key": f"{record.provider}:{record.unit_id}:{record.reference_month}",
            },
            "notification_condition": {
                "condition_met": condition_met,
                "reason": "new_unpaid_boleto" if condition_met else "no_new_unpaid_boleto",
            },
            "record_id": record.id,
            "detected_at": datetime.utcnow().isoformat() + "Z",
        }

    def store_utility_bill_record(
        self,
        extracted: Dict[str, Any],
        config: Dict[str, Any],
        *,
        flow_run_id: Optional[int],
    ) -> Dict[str, Any]:
        record_result = self._upsert_bill(extracted, config, flow_run_id=flow_run_id)
        return self._build_bill_store_output(record_result, extracted)

    def store_financial_record(
        self,
        record: Dict[str, Any],
        config: Dict[str, Any],
        *,
        flow_run_id: Optional[int],
    ) -> Dict[str, Any]:
        record_type = str(
            record.get("record_kind")
            or record.get("record_type")
            or config.get("financial_record_kind")
            or "automation_record"
        ).strip()
        if not record_type:
            raise FinancialAutomationError("financial_record_kind_required")

        provider = str(record.get("provider") or config.get("financial_provider") or "unknown").strip()
        automation_key = str(
            record.get("automation_key")
            or record.get("automation_id")
            or config.get("financial_automation_key")
            or config.get("financial_automation_id")
            or provider
        ).strip()
        subject_key = str(
            record.get("subject_key")
            or record.get("unit_id")
            or record.get("asset")
            or config.get("financial_subject_key")
            or "default"
        ).strip()
        period_key = str(
            record.get("period_key")
            or record.get("reference_month")
            or record.get("year")
            or record.get("occurred_on")
            or record.get("date")
            or datetime.utcnow().strftime("%Y-%m")
        ).strip()
        external_id = str(record.get("external_id") or record.get("bill_id") or record.get("id") or "").strip() or None
        dedupe_key = str(
            record.get("dedupe_key")
            or config.get("financial_dedupe_key")
            or config.get("financial_record_dedupe_key")
            or ":".join(part for part in [record_type, provider, subject_key, period_key, external_id or ""] if part)
        ).strip()
        if not dedupe_key:
            raise FinancialAutomationError("financial_dedupe_key_required")

        existing = (
            self.db.query(FinancialAutomationRecord)
            .filter(
                FinancialAutomationRecord.tenant_id == self.tenant_id,
                FinancialAutomationRecord.dedupe_key == dedupe_key,
            )
            .first()
        )
        created = existing is None
        row = existing or FinancialAutomationRecord(
            tenant_id=self.tenant_id,
            record_type=record_type,
            automation_key=automation_key,
            provider=provider,
            subject_key=subject_key,
            period_key=period_key,
            dedupe_key=dedupe_key,
        )
        row.record_type = record_type
        row.automation_key = automation_key
        row.provider = provider
        row.subject_key = subject_key
        row.period_key = period_key
        row.external_id = external_id
        row.title = record.get("title") or record.get("asset") or record.get("client")
        row.status = record.get("status")
        row.amount_cents = record.get("amount_cents")
        row.currency = record.get("currency") or ("BRL" if record.get("amount_cents") is not None else None)
        row.due_date = record.get("due_date")
        row.occurred_on = record.get("occurred_on") or record.get("date")
        row.redacted_payload_json = json.dumps(_redact_financial_payload(record), ensure_ascii=False)
        row.last_flow_run_id = flow_run_id
        row.last_seen_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()

        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        condition_met = bool(created or str(config.get("financial_notify_on_update") or "").lower() == "true")
        return {
            "status": "completed",
            "success": True,
            "record_kind": record_type,
            "automation_key": row.automation_key,
            "provider": row.provider,
            "subject_key": row.subject_key,
            "period_key": row.period_key,
            "external_id": row.external_id,
            "title": row.title,
            "record_status": row.status,
            "amount_cents": row.amount_cents,
            "amount_display": _format_brl(row.amount_cents),
            "currency": row.currency,
            "due_date": row.due_date,
            "occurred_on": row.occurred_on,
            "redacted": True,
            "dedupe": {
                "created": created,
                "updated": not created,
                "dedupe_key": row.dedupe_key,
            },
            "notification_condition": {
                "condition_met": condition_met,
                "reason": "new_record" if created else "existing_record",
            },
            "record_id": row.id,
            "detected_at": datetime.utcnow().isoformat() + "Z",
        }

    def _normalize_consigaz_bills(self, boleto_json: Dict[str, Any], nota_json: Dict[str, Any]) -> list[Dict[str, Any]]:
        bill_map: dict[str, Dict[str, Any]] = {}

        def merge_preferred(current: Any, next_value: Any) -> Any:
            return current if next_value in (None, "") else next_value

        def upsert_bill(bill_id: str, patch: Dict[str, Any]) -> None:
            if not bill_id:
                return
            existing = bill_map.get(
                bill_id,
                {
                    "bill_id": bill_id,
                    "reference_month": "",
                    "due_date": "",
                    "amount": "",
                    "status": "",
                    "barcode": "",
                    "issuer": self.CONSIGAZ_ISSUER,
                },
            )
            bill_map[bill_id] = {
                "bill_id": merge_preferred(existing.get("bill_id"), patch.get("bill_id")),
                "reference_month": merge_preferred(existing.get("reference_month"), patch.get("reference_month")),
                "due_date": merge_preferred(existing.get("due_date"), patch.get("due_date")),
                "amount": merge_preferred(existing.get("amount"), patch.get("amount")),
                "status": merge_preferred(existing.get("status"), patch.get("status")),
                "barcode": merge_preferred(existing.get("barcode"), patch.get("barcode")),
                "issuer": merge_preferred(existing.get("issuer"), patch.get("issuer")),
            }

        nota_rows = (((nota_json.get("Notas") or {}).get("NotasFiscais")) or [])
        for nota in (nota_rows if isinstance(nota_rows, list) else []):
            if not isinstance(nota, dict):
                continue
            duplicatas = nota.get("Duplicatas") if isinstance(nota.get("Duplicatas"), list) else []
            duplicata = duplicatas[0] if duplicatas else {}
            bill_id = str(nota.get("nr-nota-fis") or duplicata.get("nr-nota-fis") or "").strip()
            due_date = _to_br_date(duplicata.get("dt-venc") or duplicata.get("dt_venc"))
            issue_date = str(nota.get("dt-emis-nota") or "").strip()
            status = str(duplicata.get("situacao") or nota.get("situacao") or "").strip()
            upsert_bill(
                bill_id,
                {
                    "bill_id": bill_id,
                    "reference_month": _reference_month_yyyy_mm(nota.get("referencia"), issue_date or due_date),
                    "due_date": due_date,
                    "amount": self._normalize_consigaz_amount(
                        nota.get("vl-tot-nota") or duplicata.get("vl-dup") or duplicata.get("valor")
                    ),
                    "status": status or self._infer_consigaz_status(status, due_date),
                    "issuer": self.CONSIGAZ_ISSUER,
                },
            )

        boleto_rows = (((boleto_json.get("dsRetorno") or {}).get("tt-cliente-retorno")) or [])
        for boleto in (boleto_rows if isinstance(boleto_rows, list) else []):
            if not isinstance(boleto, dict):
                continue
            dados_rows = boleto.get("tt-dados-gerais") if isinstance(boleto.get("tt-dados-gerais"), list) else []
            dados = dados_rows[0] if dados_rows else {}
            bill_id = str(
                boleto.get("cod_tit_acr")
                or dados.get("cod_tit_acr")
                or dados.get("cod-tit-acr")
                or ""
            ).strip()
            due_date = _to_br_date(dados.get("vencimento") or boleto.get("vencimento"))
            upsert_bill(
                bill_id,
                {
                    "bill_id": bill_id,
                    "reference_month": _reference_month_yyyy_mm(dados.get("referencia"), due_date),
                    "due_date": due_date,
                    "amount": self._normalize_consigaz_amount(
                        dados.get("valor-total") or boleto.get("valor-total") or boleto.get("saldo")
                    ),
                    "status": str(boleto.get("situacao_pagto") or "").strip(),
                    "barcode": _digits_only(
                        dados.get("linha-digitavel")
                        or dados.get("codigo-barras")
                        or boleto.get("linha-digitavel")
                        or boleto.get("codigo-barras")
                    ),
                    "issuer": self.CONSIGAZ_ISSUER,
                },
            )

        bills = [
            {**bill, "status": self._infer_consigaz_status(bill.get("status"), bill.get("due_date"))}
            for bill in bill_map.values()
            if bill.get("reference_month") and bill.get("amount")
        ]
        return sorted(bills, key=lambda bill: _to_iso_date(bill.get("due_date")) or f"{bill.get('reference_month')}-99")

    def _normalize_medsenior_bills(self, rows: list[Any], copy_map: Dict[str, str]) -> list[Dict[str, Any]]:
        bills: list[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            bill_id = str(row.get("nossoNumero") or row.get("id") or "").strip()
            due_date = _to_br_date(row.get("dataVencimentoProrrogado") or row.get("dataVencimento"))
            amount = self._normalize_medsenior_amount(row.get("valorDocumento"))
            barcode = _digits_only(
                row.get("linhaDigitavel")
                or row.get("codigoBarras")
                or copy_map.get(bill_id)
            )
            bill = {
                "bill_id": bill_id,
                "reference_month": _reference_month_yyyy_mm(row.get("mensalidade"), due_date),
                "due_date": due_date,
                "amount": amount,
                "status": str(row.get("status") or "").strip(),
                "barcode": barcode,
                "issuer": str(
                    row.get("razaoSocialOperadora")
                    or row.get("beneficiario")
                    or row.get("nomeBeneficiario")
                    or self.MEDSENIOR_ISSUER
                ).strip(),
            }
            if bill["reference_month"] and bill["amount"]:
                bills.append(bill)
        return sorted(bills, key=lambda bill: _to_iso_date(bill.get("due_date")) or f"{bill.get('reference_month')}-99")

    @staticmethod
    def _normalize_medsenior_amount(value: Any) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, (int, float)):
            return f"{value:.2f}"
        raw = str(value).strip()
        if not raw:
            return ""
        if "," in raw and "." in raw:
            normalized = raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            normalized = raw.replace(".", "").replace(",", ".")
        else:
            normalized = raw
        try:
            return f"{Decimal(normalized):.2f}"
        except (InvalidOperation, ValueError):
            return raw

    @staticmethod
    def _normalize_consigaz_amount(value: Any) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, (int, float)):
            return f"{value:.2f}"
        raw = str(value).strip()
        if not raw:
            return ""
        if "," in raw and "." in raw:
            normalized = raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            normalized = raw.replace(".", "").replace(",", ".")
        else:
            normalized = raw
        try:
            return f"{Decimal(normalized):.2f}"
        except (InvalidOperation, ValueError):
            return raw

    @staticmethod
    def _infer_consigaz_status(status: Optional[str], due_date_br: Optional[str]) -> str:
        raw = str(status or "").strip()
        if raw:
            return raw
        due_iso = _to_iso_date(due_date_br)
        today_iso = date.today().isoformat()
        return "Vencido" if due_iso and due_iso < today_iso else "Aberto"

    def _upsert_bill(self, extracted: Dict[str, Any], config: Dict[str, Any], *, flow_run_id: Optional[int]) -> Dict[str, Any]:
        if extracted.get("no_open_bills"):
            reference_month = datetime.utcnow().strftime("%m/%Y")
        else:
            reference_month = _to_reference_month(
                extracted.get("reference_month") or extracted.get("period_key") or extracted.get("month"),
                extracted.get("due_date"),
            )
        if not reference_month:
            raise FinancialAutomationError("reference_month_not_detected")

        provider = str(extracted.get("provider") or config.get("financial_provider") or self.MODERNA_PROVIDER)
        automation_key = str(
            extracted.get("automation_key")
            or extracted.get("automation_id")
            or config.get("financial_automation_key")
            or config.get("financial_automation_id")
            or self.MODERNA_AUTOMATION_ID
        )
        unit_id = str(extracted.get("unit_id") or config.get("financial_unit_id") or "0204")
        barcode = extracted.get("barcode") or ""
        encrypted_barcode = None
        if barcode:
            encrypted_barcode = get_password_vault_encryptor(self.db).encrypt(barcode, self.tenant_id)

        existing = (
            self.db.query(FinancialUtilityBill)
            .filter(
                FinancialUtilityBill.tenant_id == self.tenant_id,
                FinancialUtilityBill.provider == provider,
                FinancialUtilityBill.unit_id == unit_id,
                FinancialUtilityBill.reference_month == reference_month,
            )
            .first()
        )
        created = existing is None
        record = existing or FinancialUtilityBill(
            tenant_id=self.tenant_id,
            automation_key=automation_key,
            provider=provider,
            unit_id=unit_id,
            reference_month=reference_month,
        )

        previous_barcode_preview = record.barcode_preview
        record.automation_key = automation_key
        record.asset = extracted.get("asset")
        record.address = extracted.get("address")
        record.due_date = _to_br_date(extracted.get("due_date")) or None
        record.amount_cents = extracted.get("amount_cents")
        record.currency = "BRL"
        record.status = extracted.get("status")
        if encrypted_barcode:
            record.barcode_encrypted = encrypted_barcode
            record.barcode_preview = _barcode_preview(barcode)
        record.raw_payload_json = json.dumps(
            {
                "amount": extracted.get("amount"),
                "all_bills_count": extracted.get("all_bills_count"),
                "barcode_detected": bool(barcode),
                "bill_id": extracted.get("bill_id"),
                "issuer": extracted.get("issuer"),
                "no_open_bills": bool(extracted.get("no_open_bills")),
                "selected_delivery_location": extracted.get("selected_delivery_location"),
            },
            ensure_ascii=False,
        )
        record.last_flow_run_id = flow_run_id
        record.last_seen_at = datetime.utcnow()
        record.updated_at = datetime.utcnow()

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        return {
            "record": record,
            "created": created,
            "updated": not created,
            "barcode_changed": bool(record.barcode_preview and record.barcode_preview != previous_barcode_preview),
        }

    def _maybe_create_notification(self, record_result: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        record: FinancialUtilityBill = record_result["record"]
        condition_met = bool(
            (record_result["created"] or record_result["barcode_changed"])
            and record.barcode_preview
            and not _is_paid_status(record.status)
        )
        if not condition_met:
            return {"condition_met": False, "created_event_id": None, "skipped_reason": "no_new_unpaid_boleto"}

        if not bool(config.get("financial_notification_enabled", False)):
            return {"condition_met": True, "created_event_id": None, "skipped_reason": "notification_disabled"}

        recipient = str(config.get("financial_notification_recipient") or "").strip()
        if not recipient:
            return {"condition_met": True, "created_event_id": None, "skipped_reason": "missing_recipient"}

        message = (
            f"Novo boleto detectado: {record.asset or record.unit_id} "
            f"{record.reference_month} vence {record.due_date or 'sem vencimento'} "
            f"no valor {_format_brl(record.amount_cents) or 'não informado'}. "
            f"Linha digitável: {record.barcode_preview}."
        )
        event = ScheduledEvent(
            tenant_id=self.tenant_id,
            creator_type="USER",
            creator_id=int(config.get("financial_notification_creator_id") or 1),
            event_type="NOTIFICATION",
            scheduled_at=datetime.utcnow(),
            status="PENDING",
            payload=json.dumps(
                {
                    "agent_id": config.get("financial_notification_agent_id") or config.get("agent_id") or 1,
                    "recipient_raw": recipient,
                    "reminder_text": message,
                    "message_template": "{reminder_text}",
                    "source": "financial_record_store",
                    "record_id": record.id,
                },
                ensure_ascii=False,
            ),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return {"condition_met": True, "created_event_id": event.id, "skipped_reason": None}
