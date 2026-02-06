"""
Integration Tests: Prompt System
Tests prompt system with real database:
- Tone preset creation and usage
- Persona with custom/preset tones
- Prompt override hierarchy
- Variable interpolation
"""

import pytest
from models import Agent, Contact, TonePreset, Persona, Config
from models_rbac import Tenant


@pytest.mark.integration
class TestPromptSystemIntegration:
    """Integration tests for prompt system with database."""

    def test_create_tone_preset_and_assign_to_persona(self, integration_db, sample_tenant):
        """Test creating tone preset and assigning to persona."""
        tenant, user = sample_tenant

        # Create tone preset
        tone = TonePreset(
            name="Casual",
            description="Use casual, friendly language",
            is_system=False,
            tenant_id=tenant.id
        )
        integration_db.add(tone)
        integration_db.commit()
        integration_db.refresh(tone)

        # Create persona with tone preset
        persona = Persona(
            name="Casual Assistant",
            description="A relaxed helper",
            tone_preset_id=tone.id,
            enabled_skills=[],
            is_active=True,
            tenant_id=tenant.id
        )
        integration_db.add(persona)
        integration_db.commit()

        # Verify relationship
        loaded_persona = integration_db.query(Persona).filter(
            Persona.id == persona.id
        ).first()
        assert loaded_persona.tone_preset_id == tone.id

        # Verify tone can be retrieved
        loaded_tone = integration_db.query(TonePreset).filter(
            TonePreset.id == loaded_persona.tone_preset_id
        ).first()
        assert loaded_tone.name == "Casual"
        assert loaded_tone.description == "Use casual, friendly language"

    def test_persona_with_custom_tone(self, integration_db, sample_tenant):
        """Test persona with custom tone (no preset)."""
        tenant, user = sample_tenant

        # Create persona with custom tone
        persona = Persona(
            name="Pirate Assistant",
            description="Talks like a pirate",
            custom_tone="Speak like a pirate, use nautical terms",
            enabled_skills=[],
            is_active=True,
            tenant_id=tenant.id
        )
        integration_db.add(persona)
        integration_db.commit()

        # Verify custom tone stored
        loaded = integration_db.query(Persona).filter(Persona.id == persona.id).first()
        assert loaded.custom_tone == "Speak like a pirate, use nautical terms"
        assert loaded.tone_preset_id is None

    def test_prompt_override_hierarchy(self, integration_db, sample_tenant):
        """Test prompt override: Agent > Config default."""
        tenant, user = sample_tenant

        # Create global config
        config = integration_db.query(Config).first()
        if not config:
            config = Config(
                id=1,
                messages_db_path="/tmp/test.db",
                system_prompt="Global default prompt"
            )
            integration_db.add(config)
            integration_db.commit()
        else:
            config.system_prompt = "Global default prompt"
            integration_db.commit()

        # Create contact
        contact = Contact(
            friendly_name="User",
            phone_number="+1111",
            tenant_id=tenant.id
        )
        integration_db.add(contact)
        integration_db.commit()

        # Create agent with empty prompt (application logic uses global default)
        # Note: system_prompt is NOT NULL in database, so we use empty string
        # The application logic should check: agent.system_prompt or config.system_prompt
        agent_default = Agent(
            contact_id=contact.id,
            system_prompt="",  # Empty - application uses global default
            model_provider="anthropic",
            model_name="claude-3.5-sonnet",
            tenant_id=tenant.id
        )
        integration_db.add(agent_default)

        # Create contact 2
        contact2 = Contact(
            friendly_name="User2",
            phone_number="+2222",
            tenant_id=tenant.id
        )
        integration_db.add(contact2)
        integration_db.commit()

        # Create agent WITH custom prompt (should override global)
        agent_custom = Agent(
            contact_id=contact2.id,
            system_prompt="Custom agent prompt",
            model_provider="anthropic",
            model_name="claude-3.5-sonnet",
            tenant_id=tenant.id
        )
        integration_db.add(agent_custom)
        integration_db.commit()

        # Verify hierarchy (empty string is falsy, so falls back to global)
        effective_prompt_default = agent_default.system_prompt or config.system_prompt
        effective_prompt_custom = agent_custom.system_prompt or config.system_prompt

        assert effective_prompt_default == "Global default prompt", f"Expected global default, got: {effective_prompt_default}"
        assert effective_prompt_custom == "Custom agent prompt", f"Expected custom prompt, got: {effective_prompt_custom}"

    def test_variable_interpolation_in_prompts(self, integration_db, sample_tenant):
        """Test {{TONE}} and {{PERSONA}} variable interpolation."""
        tenant, user = sample_tenant

        # Create tone
        tone = TonePreset(
            name="Formal",
            description="Use formal, professional language",
            tenant_id=tenant.id
        )
        integration_db.add(tone)
        integration_db.commit()

        # Create persona
        persona = Persona(
            name="Business Assistant",
            description="Helps with business tasks",
            tone_preset_id=tone.id,
            enabled_skills=[],
            tenant_id=tenant.id
        )
        integration_db.add(persona)
        integration_db.commit()

        # Create contact
        contact = Contact(
            friendly_name="Client",
            phone_number="+3333",
            tenant_id=tenant.id
        )
        integration_db.add(contact)
        integration_db.commit()

        # Create agent with template prompt
        agent = Agent(
            contact_id=contact.id,
            persona_id=persona.id,
            system_prompt="You are a {{PERSONA}}. {{TONE}}",
            tone_preset_id=tone.id,
            model_provider="anthropic",
            model_name="claude-3.5-sonnet",
            tenant_id=tenant.id
        )
        integration_db.add(agent)
        integration_db.commit()

        # Simulate interpolation
        prompt = agent.system_prompt
        loaded_tone = integration_db.query(TonePreset).filter(
            TonePreset.id == agent.tone_preset_id
        ).first()
        loaded_persona = integration_db.query(Persona).filter(
            Persona.id == agent.persona_id
        ).first()

        if loaded_persona:
            prompt = prompt.replace("{{PERSONA}}", loaded_persona.name)
        if loaded_tone:
            prompt = prompt.replace("{{TONE}}", loaded_tone.description)

        expected = "You are a Business Assistant. Use formal, professional language"
        assert prompt == expected

    def test_tone_preset_usage_count(self, integration_db, sample_tenant):
        """Test tracking tone preset usage across agents."""
        tenant, user = sample_tenant

        # Create tone
        tone = TonePreset(
            name="Helpful",
            description="Be helpful and supportive",
            tenant_id=tenant.id
        )
        integration_db.add(tone)
        integration_db.commit()

        # Create multiple contacts and agents using same tone
        for i in range(3):
            contact = Contact(
                friendly_name=f"Contact {i}",
                phone_number=f"+{1000+i}",
                tenant_id=tenant.id
            )
            integration_db.add(contact)
            integration_db.commit()

            agent = Agent(
                contact_id=contact.id,
                tone_preset_id=tone.id,
                system_prompt=f"Agent {i}",
                model_provider="anthropic",
                model_name="claude-3.5-sonnet",
                tenant_id=tenant.id
            )
            integration_db.add(agent)

        integration_db.commit()

        # Count usage
        usage_count = integration_db.query(Agent).filter(
            Agent.tone_preset_id == tone.id
        ).count()

        assert usage_count == 3

    def test_persona_skill_configuration(self, integration_db, sample_tenant):
        """Test persona with enabled skills configuration."""
        tenant, user = sample_tenant

        # Create persona with skills
        persona = Persona(
            name="Research Assistant",
            description="Helps with research",
            enabled_skills=[1, 2, 5],  # Skill IDs
            enabled_custom_tools=[10, 11],
            enabled_knowledge_bases=[100],
            is_active=True,
            tenant_id=tenant.id
        )
        integration_db.add(persona)
        integration_db.commit()
        integration_db.refresh(persona)

        # Verify skills stored as JSON
        assert persona.enabled_skills == [1, 2, 5]
        assert persona.enabled_custom_tools == [10, 11]
        assert persona.enabled_knowledge_bases == [100]

    def test_system_vs_custom_tone_presets(self, integration_db):
        """Test distinction between system and custom tone presets."""
        # Create system tone (no tenant)
        system_tone = TonePreset(
            name="Default",
            description="Default system tone",
            is_system=True,
            tenant_id=None
        )
        integration_db.add(system_tone)

        # Create custom tone for tenant
        custom_tone = TonePreset(
            name="Custom",
            description="Custom tenant tone",
            is_system=False,
            tenant_id="tenant1"
        )
        integration_db.add(custom_tone)
        integration_db.commit()

        # Query system tones (should work for all tenants)
        system_tones = integration_db.query(TonePreset).filter(
            TonePreset.is_system == True
        ).all()

        # Query tenant-specific tones
        tenant_tones = integration_db.query(TonePreset).filter(
            TonePreset.tenant_id == "tenant1"
        ).all()

        assert len(system_tones) >= 1
        assert len(tenant_tones) == 1
        assert system_tones[0].name == "Default"
        assert tenant_tones[0].name == "Custom"

    def test_persona_tenant_isolation(self, integration_db):
        """Test personas are isolated by tenant."""
        # Create two tenants
        tenant1 = Tenant(id="tenant1", name="Org 1", slug="org-1")
        tenant2 = Tenant(id="tenant2", name="Org 2", slug="org-2")
        integration_db.add_all([tenant1, tenant2])
        integration_db.commit()

        # Create persona for tenant1
        persona1 = Persona(
            name="Persona 1",
            description="For tenant 1",
            enabled_skills=[],
            tenant_id=tenant1.id
        )

        # Create persona for tenant2
        persona2 = Persona(
            name="Persona 2",
            description="For tenant 2",
            enabled_skills=[],
            tenant_id=tenant2.id
        )
        integration_db.add_all([persona1, persona2])
        integration_db.commit()

        # Query personas for each tenant
        t1_personas = integration_db.query(Persona).filter(
            Persona.tenant_id == tenant1.id
        ).all()
        t2_personas = integration_db.query(Persona).filter(
            Persona.tenant_id == tenant2.id
        ).all()

        assert len(t1_personas) == 1
        assert len(t2_personas) == 1
        assert t1_personas[0].name == "Persona 1"
        assert t2_personas[0].name == "Persona 2"
