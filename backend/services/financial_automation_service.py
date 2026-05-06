"""Programmatic financial automation runners for Flow steps."""

from __future__ import annotations

import httpx
import hashlib
import json
import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
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
    """Tenant-scoped runners and persistence for financial utility automations."""

    MODERNA_AUTOMATION_ID = "cond_sao_blas_204_boleto_condominio"
    MODERNA_PROVIDER = "moderna"
    MODERNA_LOGIN_URL = "https://modernaadm.superlogica.net/clients/areadocondomino/"
    CONSIGAZ_AUTOMATION_ID = "consigaz_gas_cond_sao_blas_204"
    CONSIGAZ_PROVIDER = "consigaz"
    CONSIGAZ_BASE_API = "https://itdna.grupomir.com.br/consigaz"
    CONSIGAZ_BASIC_AUTH_ENV = "TSN_CONSIGAZ_BASIC_AUTH"
    CONSIGAZ_ISSUER = "Consigaz - Distribuidora de Gas Ltda - Barueri"
    MEDSENIOR_AUTOMATION_ID = "medsenior_samedil_plano_saude_mae"
    MEDSENIOR_PROVIDER = "medsenior"
    MEDSENIOR_KEYCLOAK_BASE = "https://seguranca.medsenior.com.br/auth"
    MEDSENIOR_REALM = "MilSeniorProd"
    MEDSENIOR_CLIENT_ID = "portalcliente-web"
    MEDSENIOR_BASE_API = "https://portaldocliente-api.cloud.medsenior.com.br"
    MEDSENIOR_PORTAL_WEB_ORIGIN = "D86A23C6-2FD6-40A1-9568-650982AC33FE"
    MEDSENIOR_ISSUER = "Medsenior / Samedil"

    def __init__(self, db: Session, *, tenant_id: str) -> None:
        if not tenant_id:
            raise FinancialAutomationError("tenant_id_required")
        self.db = db
        self.tenant_id = tenant_id

    async def run_moderna_condominio(self, config: Dict[str, Any], *, flow_run_id: Optional[int] = None) -> Dict[str, Any]:
        credentials = self._resolve_credentials(config)
        extracted = await self._extract_moderna_condominio(credentials, config)
        record_result = self._upsert_bill(extracted, config, flow_run_id=flow_run_id)
        return self._build_output(record_result, extracted, config)

    async def run_consigaz_sao_blas(self, config: Dict[str, Any], *, flow_run_id: Optional[int] = None) -> Dict[str, Any]:
        credentials = self._resolve_credentials(
            config,
            require_password=False,
            username_fields=[config.get("financial_username_field"), "username", "cpf", "email"],
            password_fields=[config.get("financial_password_field"), "codigo_client", "codigo_cliente"],
        )
        extracted = await self._extract_consigaz_sao_blas(credentials, config)
        record_result = self._upsert_bill(extracted, config, flow_run_id=flow_run_id)
        return self._build_output(record_result, extracted, config)

    async def run_medsenior_samedil(self, config: Dict[str, Any], *, flow_run_id: Optional[int] = None) -> Dict[str, Any]:
        credentials = self._resolve_credentials(
            config,
            username_fields=[config.get("financial_username_field"), "username", "cpf", "email"],
            password_fields=[config.get("financial_password_field"), "password", "senha"],
        )
        extracted = await self._extract_medsenior_samedil(credentials, config)
        record_result = self._upsert_bill(extracted, config, flow_run_id=flow_run_id)
        return self._build_output(record_result, extracted, config)

    def _build_output(
        self,
        record_result: Dict[str, Any],
        extracted: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        notification = self._maybe_create_notification(record_result, config)

        record = record_result["record"]
        return {
            "status": "completed",
            "success": True,
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
            "notification": notification,
            "record_id": record.id,
            "detected_at": datetime.utcnow().isoformat() + "Z",
        }

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

    def _resolve_credentials(
        self,
        config: Dict[str, Any],
        *,
        require_password: bool = True,
        username_fields: Optional[list[Optional[str]]] = None,
        password_fields: Optional[list[Optional[str]]] = None,
    ) -> Dict[str, str]:
        integration_id = config.get("financial_password_vault_integration_id") or config.get("password_vault_integration_id")
        item_ref = config.get("financial_password_vault_item_id") or config.get("financial_password_vault_item_title")
        vault = config.get("financial_password_vault_vault_id") or config.get("financial_password_vault_vault_name")
        if not integration_id or not item_ref:
            raise FinancialAutomationError("password_vault_credentials_required")

        service = PasswordVaultService(self.db, tenant_id=self.tenant_id)
        integration = service.load_integration(int(integration_id), require_active=True)
        username_fields = username_fields or [config.get("financial_username_field"), "email", "username"]
        password_fields = password_fields or [config.get("financial_password_field"), "password", "senha"]

        username = self._first_secret_value(service, integration, item_ref=item_ref, vault=vault, field_names=username_fields)
        password = self._first_secret_value(service, integration, item_ref=item_ref, vault=vault, field_names=password_fields)
        if not username or (require_password and not password):
            raise FinancialAutomationError("credentials_missing_required_fields")
        credentials = {"username": username, "email": username}
        if password:
            credentials["password"] = password
            credentials["customer_code"] = password
        return credentials

    @staticmethod
    def _first_secret_value(
        service: PasswordVaultService,
        integration: Any,
        *,
        item_ref: str,
        vault: Optional[str],
        field_names: list[Optional[str]],
    ) -> Optional[str]:
        last_error: Optional[Exception] = None
        for field_name in field_names:
            if not field_name:
                continue
            try:
                return service.resolve_field_value(
                    integration,
                    item_ref=item_ref,
                    field_name=field_name,
                    vault=vault,
                )
            except PasswordVaultError as exc:
                last_error = exc
                continue
        if last_error:
            logger.debug("Secret field resolution failed: %s", last_error)
        return None

    async def _extract_moderna_condominio(self, credentials: Dict[str, str], config: Dict[str, Any]) -> Dict[str, Any]:
        from playwright.async_api import async_playwright

        timeout_ms = int(config.get("financial_browser_timeout_ms") or 30000)
        unit_id = str(config.get("financial_unit_id") or "0204")
        asset = str(config.get("financial_asset") or "AP Ed. San Blass")
        address = str(config.get("financial_address") or "Rua Piratininga 111, Praia da Costa, Vila Velha")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-setuid-sandbox"],
            )
            try:
                context = await browser.new_context(viewport={"width": 1365, "height": 900})
                page = await context.new_page()
                page.set_default_timeout(timeout_ms)

                await page.goto(self.MODERNA_LOGIN_URL, wait_until="domcontentloaded")
                await page.fill("input#email[name='email']", credentials["email"])
                await page.click("input#salvar[type='submit']")
                await page.wait_for_selector("input#senha", timeout=10000)
                await page.fill("input#senha[name='senha']", credentials["password"])
                await page.click("input#salvar[type='submit']")
                await page.wait_for_url(re.compile(r".*/cobranca.*"), timeout=20000)
                await page.wait_for_selector(".cobrancas", timeout=15000)

                bills_raw = await page.evaluate(
                    """() => {
                      const empty = document.querySelector('.conteudo-nenhuma-cobranca');
                      if (empty && empty.offsetParent !== null) return [];
                      const pagos = document.querySelector('.pagos');
                      const links = Array.from(document.querySelectorAll('a.bloco-grid-cobrancas'));
                      return links
                        .filter(a => !(pagos && pagos.contains(a)))
                        .map((a, index) => ({
                          index,
                          unit: a.querySelector('.unidade .numero')?.textContent?.trim() || '',
                          due_date: (a.querySelector('.infos .vencimento')?.textContent || '').trim().replace('Vencimento em ', ''),
                          status: a.querySelector('.infos .situacao')?.textContent?.trim() || '',
                          amount: a.querySelector('.valor')?.textContent?.trim() || ''
                        }));
                    }"""
                )
                bills = bills_raw if isinstance(bills_raw, list) else []
                if not bills:
                    return {
                        "unit_id": unit_id,
                        "asset": asset,
                        "address": address,
                        "no_open_bills": True,
                        "status": "no_open_bills",
                    }

                selected = bills[0]
                await page.evaluate(
                    """() => {
                      const pagos = document.querySelector('.pagos');
                      const link = Array.from(document.querySelectorAll('a.bloco-grid-cobrancas'))
                        .find(a => !(pagos && pagos.contains(a)));
                      if (!link) throw new Error('no_open_bill_link');
                      link.click();
                    }"""
                )
                await page.wait_for_selector(
                    "#Areadocondomino_Forms_Recebimentos_ImprimirSegundaVia #salvar, .modal input#salvar",
                    timeout=10000,
                )
                segunda_via_url = await page.evaluate(
                    """() => new Promise(resolve => {
                      let popupUrl = '';
                      const origOpen = window.open;
                      window.open = function(url) {
                        popupUrl = url || '';
                        return { document: { write() {}, close() {} }, focus() {}, close() {} };
                      };
                      const btn = document.querySelector('#Areadocondomino_Forms_Recebimentos_ImprimirSegundaVia #salvar, .modal input#salvar');
                      if (!btn) { window.open = origOpen; resolve(''); return; }
                      btn.click();
                      setTimeout(() => {
                        window.open = origOpen;
                        if (popupUrl && !popupUrl.startsWith('http')) popupUrl = window.location.origin + popupUrl;
                        resolve(popupUrl || '');
                      }, 3000);
                    })"""
                )
                barcode = ""
                if segunda_via_url:
                    await page.goto(str(segunda_via_url), wait_until="domcontentloaded")
                    barcode = await page.evaluate(
                        """() => new Promise(resolve => {
                          let attempts = 0;
                          const check = () => {
                            attempts++;
                            const el = document.querySelector('#section-linhadigitavel .copy-text, #section-linhadigitavel, [class*=linhadigitavel], [class*=linha-digitavel]');
                            if (el) {
                              const txt = (el.textContent || '').trim().replace(/[\\s.]/g, '');
                              if (txt.length >= 47) { resolve(txt); return; }
                            }
                            const allText = document.body.innerText || '';
                            const m = allText.match(/(\\d{5}\\.\\d{5}\\s*\\d{5}\\.\\d{6}\\s*\\d{5}\\.\\d{6}\\s*\\d\\s*\\d{14})/);
                            if (m) { resolve(m[1].replace(/[\\s.]/g, '')); return; }
                            if (attempts < 10) setTimeout(check, 1000);
                            else resolve('');
                          };
                          setTimeout(check, 3000);
                        })"""
                    )

                return {
                    "unit_id": unit_id,
                    "asset": asset,
                    "address": address,
                    "due_date": selected.get("due_date"),
                    "reference_month": _reference_month_from_due_date(selected.get("due_date")),
                    "amount": selected.get("amount"),
                    "amount_cents": _parse_brl_cents(selected.get("amount")),
                    "status": selected.get("status"),
                    "barcode": re.sub(r"\D", "", str(barcode or "")),
                    "all_bills_count": len(bills),
                }
            finally:
                await browser.close()

    async def _extract_consigaz_sao_blas(self, credentials: Dict[str, str], config: Dict[str, Any]) -> Dict[str, Any]:
        timeout_ms = int(config.get("financial_browser_timeout_ms") or 30000)
        unit_id = str(config.get("financial_unit_id") or "AP0204")
        asset = str(config.get("financial_asset") or "AP Ed. San Blass")
        address = str(config.get("financial_address") or "R PIRATININGA, 111 AP0204")
        expected_customer_code = _digits_only(
            str(config.get("financial_customer_code") or credentials.get("customer_code") or "1051548")
        )
        expected_delivery_location = str(config.get("financial_delivery_location") or "PADRAO").strip().upper()
        cpf_cnpj = _digits_only(credentials.get("username") or credentials.get("email"))
        if not cpf_cnpj:
            raise FinancialAutomationError("consigaz_cpf_cnpj_required")
        basic_auth = str(
            config.get("basic_auth")
            or config.get("consigaz_basic_auth")
            or os.getenv(self.CONSIGAZ_BASIC_AUTH_ENV)
            or ""
        ).strip()
        if not basic_auth:
            raise FinancialAutomationError("consigaz_basic_auth_required")

        today = date.today()
        try:
            start_date = today.replace(year=today.year - 1)
        except ValueError:
            start_date = today.replace(year=today.year - 1, day=28)
        date_end = today.isoformat().replace("-", "/")
        date_start = start_date.isoformat().replace("-", "/")

        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            token_json = await self._fetch_consigaz_json(
                client,
                "GeraToken",
                headers={"Authorization": basic_auth, "Accept": "application/json"},
            )
            token = str(token_json.get("Token") or token_json.get("token") or "").strip()
            if not token:
                raise FinancialAutomationError("consigaz_token_missing")

            auth_headers = {"token": token, "Accept": "application/json"}
            local_json = await self._fetch_consigaz_json(
                client,
                "ConsultaLocalEntrega",
                params={"cpfcnpj": cpf_cnpj, "versao": "1"},
                headers=auth_headers,
            )
            local_entrega = self._select_consigaz_delivery_location(
                local_json,
                expected_customer_code=expected_customer_code,
                expected_delivery_location=expected_delivery_location,
                expected_address=address,
            )
            if not local_entrega:
                raise FinancialAutomationError("consigaz_delivery_location_not_resolved")

            boleto_json = await self._fetch_consigaz_json(
                client,
                "Consulta2ViaBoleto",
                params={
                    "cpfcnpj": cpf_cnpj,
                    "data-fim": date_end,
                    "data-ini": date_start,
                    "quitadas": "no",
                    "origem": "app-site",
                    "local-entrega": local_entrega,
                },
                headers=auth_headers,
            )
            nota_json = await self._fetch_consigaz_json(
                client,
                "ConsultaNotaFiscal",
                params={"cpfcnpj": cpf_cnpj, "data-fim": date_end, "data-ini": date_start},
                headers=auth_headers,
            )

        bills = self._normalize_consigaz_bills(boleto_json, nota_json)
        primary = next((bill for bill in bills if not _is_paid_status(bill.get("status"))), None)
        selected = primary or (bills[-1] if bills else None)
        if not selected:
            return {
                "automation_key": self.CONSIGAZ_AUTOMATION_ID,
                "provider": self.CONSIGAZ_PROVIDER,
                "unit_id": unit_id,
                "asset": asset,
                "address": address,
                "reference_month": today.strftime("%Y-%m"),
                "no_open_bills": True,
                "status": "no_pending_bills",
                "all_bills_count": 0,
                "selected_delivery_location": local_entrega,
            }

        barcode = _digits_only(selected.get("barcode"))
        return {
            "automation_key": self.CONSIGAZ_AUTOMATION_ID,
            "provider": self.CONSIGAZ_PROVIDER,
            "unit_id": unit_id,
            "asset": asset,
            "address": address,
            "bill_id": selected.get("bill_id"),
            "reference_month": selected.get("reference_month"),
            "due_date": selected.get("due_date"),
            "amount": selected.get("amount"),
            "amount_cents": _parse_brl_cents(selected.get("amount")),
            "status": selected.get("status"),
            "barcode": barcode,
            "issuer": selected.get("issuer") or self.CONSIGAZ_ISSUER,
            "all_bills_count": len(bills),
            "selected_delivery_location": local_entrega,
        }

    async def _extract_medsenior_samedil(self, credentials: Dict[str, str], config: Dict[str, Any]) -> Dict[str, Any]:
        timeout_ms = int(config.get("financial_browser_timeout_ms") or 30000)
        unit_id = str(config.get("financial_unit_id") or "Plano Saude Mae")
        asset = str(config.get("financial_asset") or "Plano Saude Mae")
        address = str(config.get("financial_address") or self.MEDSENIOR_ISSUER)
        cpf = _digits_only(credentials.get("username") or credentials.get("email"))
        password = credentials.get("password") or ""
        if not cpf or not password:
            raise FinancialAutomationError("medsenior_credentials_required")

        try:
            rows, copy_map, extraction_mode = await self._extract_medsenior_rows_via_api(
                cpf=cpf,
                password=password,
                timeout_ms=timeout_ms,
            )
        except FinancialAutomationError as exc:
            if not str(exc).startswith("medsenior_token_failed:"):
                raise
            rows, copy_map, extraction_mode = await self._extract_medsenior_rows_via_browser(
                cpf=cpf,
                password=password,
                timeout_ms=timeout_ms,
            )

        bills = self._normalize_medsenior_bills(rows, copy_map)
        primary = next((bill for bill in bills if not _is_paid_status(bill.get("status"))), None)
        selected = primary or (bills[0] if bills else None)
        if not selected:
            return {
                "automation_key": self.MEDSENIOR_AUTOMATION_ID,
                "provider": self.MEDSENIOR_PROVIDER,
                "unit_id": unit_id,
                "asset": asset,
                "address": address,
                "reference_month": date.today().strftime("%Y-%m"),
                "no_open_bills": True,
                "status": "no_pending_bills",
                "all_bills_count": 0,
                "extraction_mode": extraction_mode,
            }

        return {
            "automation_key": self.MEDSENIOR_AUTOMATION_ID,
            "provider": self.MEDSENIOR_PROVIDER,
            "unit_id": unit_id,
            "asset": asset,
            "address": address,
            "bill_id": selected.get("bill_id"),
            "reference_month": selected.get("reference_month"),
            "due_date": selected.get("due_date"),
            "amount": selected.get("amount"),
            "amount_cents": _parse_brl_cents(selected.get("amount")),
            "status": selected.get("status"),
            "barcode": _digits_only(selected.get("barcode")),
            "issuer": selected.get("issuer") or self.MEDSENIOR_ISSUER,
            "all_bills_count": len(bills),
            "extraction_mode": extraction_mode,
        }

    async def _extract_medsenior_rows_via_api(
        self,
        *,
        cpf: str,
        password: str,
        timeout_ms: int,
    ) -> tuple[list[Any], Dict[str, str], str]:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            token = await self._fetch_medsenior_access_token(client, cpf=cpf, password=password)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            list_json = await self._fetch_medsenior_json(
                client,
                "/api/v1/beneficiarios/buscar/segunda-via/boletos",
                headers=headers,
            )
            rows = list_json if isinstance(list_json, list) else list_json.get("data")
            rows = rows if isinstance(rows, list) else []
            copy_map = await self._fetch_medsenior_barcodes(client, rows, headers=headers)
        return rows, copy_map, "api_password_grant"

    async def _extract_medsenior_rows_via_browser(
        self,
        *,
        cpf: str,
        password: str,
        timeout_ms: int,
    ) -> tuple[list[Any], Dict[str, str], str]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright

        user_data_dir = self._browser_state_dir(self.MEDSENIOR_AUTOMATION_ID)
        login_url = (
            f"{self.MEDSENIOR_KEYCLOAK_BASE}/realms/{self.MEDSENIOR_REALM}/protocol/openid-connect/auth"
            f"?client_id={self.MEDSENIOR_CLIENT_ID}"
            "&redirect_uri=https%3A%2F%2Fportaldocliente.medsenior.com.br%2F"
            "&response_type=code&scope=openid"
        )

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=True,
                viewport={"width": 1365, "height": 900},
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-setuid-sandbox"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                page.set_default_timeout(timeout_ms)

                await page.goto(login_url, wait_until="domcontentloaded")
                await self._submit_medsenior_login_if_present(page, cpf=cpf, password=password, timeout_ms=timeout_ms)
                await page.goto(
                    "https://portaldocliente.medsenior.com.br/beneficiario/financeiro/boletos",
                    wait_until="domcontentloaded",
                )
                await self._submit_medsenior_login_if_present(page, cpf=cpf, password=password, timeout_ms=timeout_ms)
                await page.wait_for_selector("body", timeout=timeout_ms)

                rows = await page.evaluate(
                    """async ({ baseApi, portalWebOrigin }) => {
                      const tokenFromStorage = () => {
                        for (const key of ['@user-data', 'user-data', 'userData']) {
                          const raw = window.localStorage.getItem(key);
                          if (!raw) continue;
                          try {
                            const parsed = JSON.parse(raw);
                            if (parsed?.access_token) return parsed.access_token;
                            if (parsed?.accessToken) return parsed.accessToken;
                          } catch {}
                        }
                        return '';
                      };
                      const token = tokenFromStorage();
                      if (!token) return { authMissing: true, rows: [] };
                      const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' };
                      const listRes = await fetch(`${baseApi}/api/v1/beneficiarios/buscar/segunda-via/boletos`, { headers });
                      if (!listRes.ok) return { requestStatus: listRes.status, rows: [] };
                      const listJson = await listRes.json();
                      const rows = Array.isArray(listJson) ? listJson : Array.isArray(listJson?.data) ? listJson.data : [];
                      const isPaid = (value) => /baixad|pago|quitad|liquidad/i.test(String(value || ''));
                      await Promise.all(rows.map(async (row) => {
                        const nossoNumero = String(row?.nossoNumero || '').trim();
                        if (!nossoNumero || isPaid(row?.status)) return;
                        try {
                          const response = await fetch(`${baseApi}/api/v1/beneficiarios/boletos/copiar-codigo-barras/${nossoNumero}/${portalWebOrigin}`, { method: 'POST', headers });
                          if (!response.ok) return;
                          const text = await response.text();
                          const match = text.match(/\\d[\\d.\\s-]{42,}\\d/);
                          if (match) row.copiedBarcode = match[0].replace(/\\D/g, '');
                        } catch {}
                      }));
                      return { rows };
                    }""",
                    {"baseApi": self.MEDSENIOR_BASE_API, "portalWebOrigin": self.MEDSENIOR_PORTAL_WEB_ORIGIN},
                )
                if not isinstance(rows, dict):
                    raise FinancialAutomationError("medsenior_browser_response_invalid")
                if rows.get("authMissing"):
                    raise FinancialAutomationError("medsenior_browser_auth_missing")
                if rows.get("requestStatus"):
                    raise FinancialAutomationError(f"medsenior_browser_request_failed:{rows.get('requestStatus')}")
                raw_rows = rows.get("rows") if isinstance(rows.get("rows"), list) else []
                copy_map = {
                    str(row.get("nossoNumero") or "").strip(): _digits_only(row.get("copiedBarcode"))
                    for row in raw_rows
                    if isinstance(row, dict) and row.get("copiedBarcode")
                }
                return raw_rows, copy_map, "browser_session"
            except PlaywrightTimeoutError as exc:
                raise FinancialAutomationError("medsenior_browser_timeout") from exc
            finally:
                await context.close()

    async def _submit_medsenior_login_if_present(
        self,
        page: Any,
        *,
        cpf: str,
        password: str,
        timeout_ms: int,
    ) -> None:
        username = page.locator("input#username, input[name='username']")
        if await username.count() == 0:
            return
        await username.first.fill(cpf)
        password_input = page.locator("input#password, input[name='password']")
        if await password_input.count() == 0:
            raise FinancialAutomationError("medsenior_login_password_field_missing")
        await password_input.first.fill(password)
        await page.locator("input#kc-login, input[name='login'], button[type='submit']").first.click()
        try:
            await page.wait_for_url(re.compile(r".*portaldocliente\.medsenior\.com\.br.*"), timeout=min(timeout_ms, 20000))
        except Exception:
            if await page.locator("input#username, input[name='username']").count() > 0:
                raise FinancialAutomationError("medsenior_login_not_accepted")

    def _browser_state_dir(self, automation_key: str) -> Path:
        digest = hashlib.sha256(f"{self.tenant_id}:{automation_key}".encode("utf-8")).hexdigest()[:24]
        base_dir = Path(os.environ.get("TSN_FINANCIAL_BROWSER_STATE_DIR") or "/app/data/financial-automation-browser")
        path = base_dir / digest
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def _fetch_consigaz_json(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        *,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        response = await client.get(f"{self.CONSIGAZ_BASE_API}/{endpoint}", params=params, headers=headers)
        if response.status_code >= 400:
            raise FinancialAutomationError(f"consigaz_request_failed:{endpoint}:{response.status_code}")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def _fetch_medsenior_access_token(
        self,
        client: httpx.AsyncClient,
        *,
        cpf: str,
        password: str,
    ) -> str:
        token_url = (
            f"{self.MEDSENIOR_KEYCLOAK_BASE}/realms/{self.MEDSENIOR_REALM}"
            "/protocol/openid-connect/token"
        )
        response = await client.post(
            token_url,
            data={
                "client_id": self.MEDSENIOR_CLIENT_ID,
                "grant_type": "password",
                "username": cpf,
                "password": password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise FinancialAutomationError(f"medsenior_token_failed:{response.status_code}")
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise FinancialAutomationError("medsenior_token_missing")
        return token

    async def _fetch_medsenior_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        headers: Dict[str, str],
    ) -> Any:
        response = await client.get(f"{self.MEDSENIOR_BASE_API}{path}", headers=headers)
        if response.status_code >= 400:
            raise FinancialAutomationError(f"medsenior_request_failed:{path}:{response.status_code}")
        return response.json()

    async def _fetch_medsenior_barcodes(
        self,
        client: httpx.AsyncClient,
        rows: list[Any],
        *,
        headers: Dict[str, str],
    ) -> Dict[str, str]:
        barcodes: Dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            nosso_numero = str(row.get("nossoNumero") or "").strip()
            if not nosso_numero or _is_paid_status(row.get("status")):
                continue
            response = await client.post(
                (
                    f"{self.MEDSENIOR_BASE_API}/api/v1/beneficiarios/boletos/copiar-codigo-barras/"
                    f"{nosso_numero}/{self.MEDSENIOR_PORTAL_WEB_ORIGIN}"
                ),
                headers=headers,
            )
            if response.status_code >= 400:
                logger.info("Medsenior barcode copy skipped for bill %s: HTTP %s", nosso_numero, response.status_code)
                continue
            barcode = self._extract_barcode_from_any_payload(response.text)
            if barcode:
                barcodes[nosso_numero] = barcode
        return barcodes

    @staticmethod
    def _extract_barcode_from_any_payload(raw: str) -> str:
        if not raw:
            return ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw

        values: list[str] = []

        def collect(value: Any) -> None:
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)

        collect(parsed)
        for value in values:
            digits = _digits_only(value)
            if len(digits) >= 44:
                return digits
        return ""

    @staticmethod
    def _select_consigaz_delivery_location(
        payload: Dict[str, Any],
        *,
        expected_customer_code: str,
        expected_delivery_location: str,
        expected_address: str,
    ) -> str:
        customer_rows = (((payload.get("Cliente") or {}).get("ClienteRetorno")) or [])
        expected_address_upper = expected_address.strip().upper()
        expected_tokens = [token for token in re.split(r"\s+", expected_address_upper) if len(token) >= 3]
        scored: list[tuple[int, str]] = []
        for customer in (customer_rows if isinstance(customer_rows, list) else []):
            if not isinstance(customer, dict):
                continue
            customer_code = _digits_only(customer.get("cod-emitente"))
            delivery_rows = customer.get("ClienteEntrRetorno") or []
            if not isinstance(delivery_rows, list):
                continue
            for delivery in delivery_rows:
                if not isinstance(delivery, dict):
                    continue
                local = str(delivery.get("local-entrega") or "").strip().upper()
                address_parts = " ".join(
                    str(delivery.get(key) or "")
                    for key in ("endereco", "numero", "complemento")
                    if delivery.get(key)
                ).upper()
                score = 0
                if expected_customer_code and customer_code == expected_customer_code:
                    score += 5
                if expected_delivery_location and local == expected_delivery_location:
                    score += 3
                if expected_address_upper and expected_address_upper in address_parts:
                    score += 3
                if expected_tokens and all(token in address_parts for token in expected_tokens):
                    score += 2
                if local:
                    scored.append((score, local))
        scored.sort(key=lambda row: row[0], reverse=True)
        return scored[0][1] if scored else expected_delivery_location

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
                    "source": "financial_utility_automation",
                    "record_id": record.id,
                },
                ensure_ascii=False,
            ),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return {"condition_met": True, "created_event_id": event.id, "skipped_reason": None}
