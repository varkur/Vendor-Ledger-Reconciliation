--
-- PostgreSQL database dump
--

-- Dumped from database version 16.3
-- Dumped by pg_dump version 16.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.vlr_workflow_step_history DROP CONSTRAINT IF EXISTS vlr_workflow_step_history_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_vendor_contacts DROP CONSTRAINT IF EXISTS vlr_vendor_contacts_vendor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_resolution_records DROP CONSTRAINT IF EXISTS vlr_resolution_records_exception_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_recovery_items DROP CONSTRAINT IF EXISTS vlr_recovery_items_vendor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_recovery_items DROP CONSTRAINT IF EXISTS vlr_recovery_items_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_recovery_follow_ups DROP CONSTRAINT IF EXISTS vlr_recovery_follow_ups_recovery_item_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reconciliation_cases DROP CONSTRAINT IF EXISTS vlr_reconciliation_cases_vendor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reconciliation_cases DROP CONSTRAINT IF EXISTS vlr_reconciliation_cases_request_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reco_exceptions DROP CONSTRAINT IF EXISTS vlr_reco_exceptions_ledger_entry_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reco_exceptions DROP CONSTRAINT IF EXISTS vlr_reco_exceptions_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_portal_sign_offs DROP CONSTRAINT IF EXISTS vlr_portal_sign_offs_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_notifications DROP CONSTRAINT IF EXISTS vlr_notifications_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_match_results DROP CONSTRAINT IF EXISTS vlr_match_results_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_ledger_entries DROP CONSTRAINT IF EXISTS vlr_ledger_entries_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_column_mapping_templates DROP CONSTRAINT IF EXISTS vlr_column_mapping_templates_vendor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_automation_executions DROP CONSTRAINT IF EXISTS vlr_automation_executions_rule_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vlr_approval_records DROP CONSTRAINT IF EXISTS vlr_approval_records_case_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_details DROP CONSTRAINT IF EXISTS user_details_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.roles DROP CONSTRAINT IF EXISTS roles_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.roles DROP CONSTRAINT IF EXISTS roles_parent_role_id_fkey;
ALTER TABLE IF EXISTS ONLY public.role_permissions DROP CONSTRAINT IF EXISTS role_permissions_role_id_fkey;
ALTER TABLE IF EXISTS ONLY public.role_permissions DROP CONSTRAINT IF EXISTS role_permissions_permission_id_fkey;
ALTER TABLE IF EXISTS ONLY public.role_assignments DROP CONSTRAINT IF EXISTS role_assignments_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.role_assignments DROP CONSTRAINT IF EXISTS role_assignments_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.role_assignments DROP CONSTRAINT IF EXISTS role_assignments_role_id_fkey;
ALTER TABLE IF EXISTS ONLY public.kombu_message DROP CONSTRAINT IF EXISTS "FK_kombu_message_queue";
DROP INDEX IF EXISTS public.uq_vlr_cases_vendor_request;
DROP INDEX IF EXISTS public.ix_workflow_transitions_workflow_definition_id;
DROP INDEX IF EXISTS public.ix_workflow_transitions_from_status_id;
DROP INDEX IF EXISTS public.ix_workflow_transitions_action_code;
DROP INDEX IF EXISTS public.ix_workflow_steps_workflow_definition_id;
DROP INDEX IF EXISTS public.ix_workflow_statuses_workflow_definition_id;
DROP INDEX IF EXISTS public.ix_workflow_statuses_code;
DROP INDEX IF EXISTS public.ix_workflow_instances_workflow_definition_id;
DROP INDEX IF EXISTS public.ix_workflow_instances_entity_type;
DROP INDEX IF EXISTS public.ix_workflow_instances_entity_id;
DROP INDEX IF EXISTS public.ix_workflow_instances_current_status_id;
DROP INDEX IF EXISTS public.ix_workflow_instance_steps_instance_id;
DROP INDEX IF EXISTS public.ix_workflow_history_instance_id;
DROP INDEX IF EXISTS public.ix_workflow_history_created_at;
DROP INDEX IF EXISTS public.ix_workflow_history_action_code;
DROP INDEX IF EXISTS public.ix_workflow_definitions_entity_type;
DROP INDEX IF EXISTS public.ix_workflow_definitions_code;
DROP INDEX IF EXISTS public.ix_workflow_assignment_rules_workflow_step_id;
DROP INDEX IF EXISTS public.ix_workflow_actions_workflow_definition_id;
DROP INDEX IF EXISTS public.ix_workflow_actions_code;
DROP INDEX IF EXISTS public.ix_vlr_wf_history_to_step;
DROP INDEX IF EXISTS public.ix_vlr_wf_history_case_triggered;
DROP INDEX IF EXISTS public.ix_vlr_wf_history_case_id;
DROP INDEX IF EXISTS public.ix_vlr_vendors_vendor_code;
DROP INDEX IF EXISTS public.ix_vlr_vendors_status;
DROP INDEX IF EXISTS public.ix_vlr_vendors_company_code;
DROP INDEX IF EXISTS public.ix_vlr_vendor_contacts_vendor_id;
DROP INDEX IF EXISTS public.ix_vlr_sla_config_step;
DROP INDEX IF EXISTS public.ix_vlr_sla_config_active;
DROP INDEX IF EXISTS public.ix_vlr_settings_key;
DROP INDEX IF EXISTS public.ix_vlr_settings_company_key;
DROP INDEX IF EXISTS public.ix_vlr_settings_company_code;
DROP INDEX IF EXISTS public.ix_vlr_resolution_records_exception_id;
DROP INDEX IF EXISTS public.ix_vlr_requests_status;
DROP INDEX IF EXISTS public.ix_vlr_requests_created_date;
DROP INDEX IF EXISTS public.ix_vlr_requests_company_code;
DROP INDEX IF EXISTS public.ix_vlr_recovery_items_vendor_id;
DROP INDEX IF EXISTS public.ix_vlr_recovery_items_status;
DROP INDEX IF EXISTS public.ix_vlr_recovery_items_next_follow_up;
DROP INDEX IF EXISTS public.ix_vlr_recovery_items_case_id;
DROP INDEX IF EXISTS public.ix_vlr_recovery_follow_ups_item_id;
DROP INDEX IF EXISTS public.ix_vlr_recovery_follow_ups_item_date;
DROP INDEX IF EXISTS public.ix_vlr_portal_sign_offs_case_id;
DROP INDEX IF EXISTS public.ix_vlr_notifications_type;
DROP INDEX IF EXISTS public.ix_vlr_notifications_status;
DROP INDEX IF EXISTS public.ix_vlr_notifications_case_id;
DROP INDEX IF EXISTS public.ix_vlr_match_results_pass_number;
DROP INDEX IF EXISTS public.ix_vlr_match_results_case_id;
DROP INDEX IF EXISTS public.ix_vlr_ledger_entries_side;
DROP INDEX IF EXISTS public.ix_vlr_ledger_entries_match_id;
DROP INDEX IF EXISTS public.ix_vlr_ledger_entries_is_tds;
DROP INDEX IF EXISTS public.ix_vlr_ledger_entries_document_number;
DROP INDEX IF EXISTS public.ix_vlr_ledger_entries_derived_invoice;
DROP INDEX IF EXISTS public.ix_vlr_ledger_entries_case_id;
DROP INDEX IF EXISTS public.ix_vlr_exceptions_status;
DROP INDEX IF EXISTS public.ix_vlr_exceptions_severity;
DROP INDEX IF EXISTS public.ix_vlr_exceptions_ledger_entry_id;
DROP INDEX IF EXISTS public.ix_vlr_exceptions_case_id;
DROP INDEX IF EXISTS public.ix_vlr_doc_type_mappings_code;
DROP INDEX IF EXISTS public.ix_vlr_doc_type_mappings_category;
DROP INDEX IF EXISTS public.ix_vlr_doc_type_mappings_active;
DROP INDEX IF EXISTS public.ix_vlr_column_mapping_templates_vendor_id;
DROP INDEX IF EXISTS public.ix_vlr_cases_workflow_step;
DROP INDEX IF EXISTS public.ix_vlr_cases_vendor_id;
DROP INDEX IF EXISTS public.ix_vlr_cases_status;
DROP INDEX IF EXISTS public.ix_vlr_cases_request_id;
DROP INDEX IF EXISTS public.ix_vlr_cases_is_overdue;
DROP INDEX IF EXISTS public.ix_vlr_cases_created_date;
DROP INDEX IF EXISTS public.ix_vlr_automation_rules_is_active;
DROP INDEX IF EXISTS public.ix_vlr_automation_rules_company_code;
DROP INDEX IF EXISTS public.ix_vlr_automation_executions_rule_id;
DROP INDEX IF EXISTS public.ix_vlr_audit_events_timestamp_event_type;
DROP INDEX IF EXISTS public.ix_vlr_audit_events_timestamp;
DROP INDEX IF EXISTS public.ix_vlr_audit_events_event_type;
DROP INDEX IF EXISTS public.ix_vlr_audit_events_case_id;
DROP INDEX IF EXISTS public.ix_vlr_audit_events_actor_username;
DROP INDEX IF EXISTS public.ix_vlr_approval_records_case_id;
DROP INDEX IF EXISTS public.ix_users_username;
DROP INDEX IF EXISTS public.ix_user_details_employee_id;
DROP INDEX IF EXISTS public.ix_tenants_domain;
DROP INDEX IF EXISTS public.ix_tenants_code;
DROP INDEX IF EXISTS public.ix_roles_tenant_id;
DROP INDEX IF EXISTS public.ix_roles_code;
DROP INDEX IF EXISTS public.ix_role_permissions_role_id;
DROP INDEX IF EXISTS public.ix_role_permissions_permission_id;
DROP INDEX IF EXISTS public.ix_role_assignments_user_id;
DROP INDEX IF EXISTS public.ix_role_assignments_tenant_id;
DROP INDEX IF EXISTS public.ix_role_assignments_role_id;
DROP INDEX IF EXISTS public.ix_permissions_scope;
DROP INDEX IF EXISTS public.ix_permissions_resource;
DROP INDEX IF EXISTS public.ix_permissions_code;
DROP INDEX IF EXISTS public.ix_kombu_message_visible;
DROP INDEX IF EXISTS public.ix_kombu_message_timestamp_id;
DROP INDEX IF EXISTS public.ix_kombu_message_timestamp;
DROP INDEX IF EXISTS public.ix_commission_claims_status;
DROP INDEX IF EXISTS public.ix_commission_claims_employee_id;
DROP INDEX IF EXISTS public.ix_commission_claims_claim_number;
DROP INDEX IF EXISTS public.ix_celery_tasksetmeta_date_done;
DROP INDEX IF EXISTS public.ix_celery_taskmeta_date_done;
DROP INDEX IF EXISTS public.ix_audit_logs_tenant_id;
DROP INDEX IF EXISTS public.ix_audit_logs_resource_type;
DROP INDEX IF EXISTS public.ix_audit_logs_created_at;
DROP INDEX IF EXISTS public.ix_audit_logs_actor_username;
DROP INDEX IF EXISTS public.ix_audit_logs_actor_id;
DROP INDEX IF EXISTS public.ix_audit_logs_action;
DROP INDEX IF EXISTS public.ix_approval_tasks_status;
DROP INDEX IF EXISTS public.ix_approval_tasks_instance_id;
DROP INDEX IF EXISTS public.ix_approval_tasks_assignee_id;
DROP INDEX IF EXISTS public.ix_approval_rules_matrix_id;
DROP INDEX IF EXISTS public.ix_approval_matrices_entity_type;
DROP INDEX IF EXISTS public.ix_approval_matrices_code;
DROP INDEX IF EXISTS public.ix_approval_delegations_delegator_id;
DROP INDEX IF EXISTS public.ix_approval_delegations_delegate_id;
DROP INDEX IF EXISTS public.ix_approval_conditions_matrix_id;
DROP INDEX IF EXISTS public.ix_approval_assignments_matrix_id;
ALTER TABLE IF EXISTS ONLY public.workflow_transitions DROP CONSTRAINT IF EXISTS workflow_transitions_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_steps DROP CONSTRAINT IF EXISTS workflow_steps_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_statuses DROP CONSTRAINT IF EXISTS workflow_statuses_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_instances DROP CONSTRAINT IF EXISTS workflow_instances_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_instance_steps DROP CONSTRAINT IF EXISTS workflow_instance_steps_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_history DROP CONSTRAINT IF EXISTS workflow_history_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_definitions DROP CONSTRAINT IF EXISTS workflow_definitions_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_assignment_rules DROP CONSTRAINT IF EXISTS workflow_assignment_rules_pkey;
ALTER TABLE IF EXISTS ONLY public.workflow_actions DROP CONSTRAINT IF EXISTS workflow_actions_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_workflow_step_history DROP CONSTRAINT IF EXISTS vlr_workflow_step_history_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_vendors DROP CONSTRAINT IF EXISTS vlr_vendors_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_vendor_contacts DROP CONSTRAINT IF EXISTS vlr_vendor_contacts_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_sla_configurations DROP CONSTRAINT IF EXISTS vlr_sla_configurations_step_name_key;
ALTER TABLE IF EXISTS ONLY public.vlr_sla_configurations DROP CONSTRAINT IF EXISTS vlr_sla_configurations_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_settings DROP CONSTRAINT IF EXISTS vlr_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_resolution_records DROP CONSTRAINT IF EXISTS vlr_resolution_records_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_recovery_items DROP CONSTRAINT IF EXISTS vlr_recovery_items_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_recovery_follow_ups DROP CONSTRAINT IF EXISTS vlr_recovery_follow_ups_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reconciliation_requests DROP CONSTRAINT IF EXISTS vlr_reconciliation_requests_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reconciliation_cases DROP CONSTRAINT IF EXISTS vlr_reconciliation_cases_portal_token_key;
ALTER TABLE IF EXISTS ONLY public.vlr_reconciliation_cases DROP CONSTRAINT IF EXISTS vlr_reconciliation_cases_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_reco_exceptions DROP CONSTRAINT IF EXISTS vlr_reco_exceptions_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_portal_sign_offs DROP CONSTRAINT IF EXISTS vlr_portal_sign_offs_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_notifications DROP CONSTRAINT IF EXISTS vlr_notifications_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_match_results DROP CONSTRAINT IF EXISTS vlr_match_results_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_ledger_entries DROP CONSTRAINT IF EXISTS vlr_ledger_entries_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_document_type_mappings DROP CONSTRAINT IF EXISTS vlr_document_type_mappings_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_document_type_mappings DROP CONSTRAINT IF EXISTS vlr_document_type_mappings_document_type_code_key;
ALTER TABLE IF EXISTS ONLY public.vlr_column_mapping_templates DROP CONSTRAINT IF EXISTS vlr_column_mapping_templates_vendor_id_key;
ALTER TABLE IF EXISTS ONLY public.vlr_column_mapping_templates DROP CONSTRAINT IF EXISTS vlr_column_mapping_templates_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_automation_rules DROP CONSTRAINT IF EXISTS vlr_automation_rules_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_automation_executions DROP CONSTRAINT IF EXISTS vlr_automation_executions_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_audit_events DROP CONSTRAINT IF EXISTS vlr_audit_events_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_approval_records DROP CONSTRAINT IF EXISTS vlr_approval_records_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY public.user_details DROP CONSTRAINT IF EXISTS user_details_user_id_key;
ALTER TABLE IF EXISTS ONLY public.user_details DROP CONSTRAINT IF EXISTS user_details_pkey;
ALTER TABLE IF EXISTS ONLY public.vlr_vendors DROP CONSTRAINT IF EXISTS uq_vendor_code_company_code;
ALTER TABLE IF EXISTS ONLY public.tenants DROP CONSTRAINT IF EXISTS tenants_pkey;
ALTER TABLE IF EXISTS ONLY public.roles DROP CONSTRAINT IF EXISTS roles_pkey;
ALTER TABLE IF EXISTS ONLY public.role_permissions DROP CONSTRAINT IF EXISTS role_permissions_pkey;
ALTER TABLE IF EXISTS ONLY public.role_assignments DROP CONSTRAINT IF EXISTS role_assignments_pkey;
ALTER TABLE IF EXISTS ONLY public.permissions DROP CONSTRAINT IF EXISTS permissions_pkey;
ALTER TABLE IF EXISTS ONLY public.kombu_queue DROP CONSTRAINT IF EXISTS kombu_queue_pkey;
ALTER TABLE IF EXISTS ONLY public.kombu_queue DROP CONSTRAINT IF EXISTS kombu_queue_name_key;
ALTER TABLE IF EXISTS ONLY public.kombu_message DROP CONSTRAINT IF EXISTS kombu_message_pkey;
ALTER TABLE IF EXISTS ONLY public.commission_claims DROP CONSTRAINT IF EXISTS commission_claims_pkey;
ALTER TABLE IF EXISTS ONLY public.celery_tasksetmeta DROP CONSTRAINT IF EXISTS celery_tasksetmeta_taskset_id_key;
ALTER TABLE IF EXISTS ONLY public.celery_tasksetmeta DROP CONSTRAINT IF EXISTS celery_tasksetmeta_pkey;
ALTER TABLE IF EXISTS ONLY public.celery_taskmeta DROP CONSTRAINT IF EXISTS celery_taskmeta_task_id_key;
ALTER TABLE IF EXISTS ONLY public.celery_taskmeta DROP CONSTRAINT IF EXISTS celery_taskmeta_pkey;
ALTER TABLE IF EXISTS ONLY public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.approval_tasks DROP CONSTRAINT IF EXISTS approval_tasks_pkey;
ALTER TABLE IF EXISTS ONLY public.approval_rules DROP CONSTRAINT IF EXISTS approval_rules_pkey;
ALTER TABLE IF EXISTS ONLY public.approval_matrices DROP CONSTRAINT IF EXISTS approval_matrices_pkey;
ALTER TABLE IF EXISTS ONLY public.approval_delegations DROP CONSTRAINT IF EXISTS approval_delegations_pkey;
ALTER TABLE IF EXISTS ONLY public.approval_conditions DROP CONSTRAINT IF EXISTS approval_conditions_pkey;
ALTER TABLE IF EXISTS ONLY public.approval_assignments DROP CONSTRAINT IF EXISTS approval_assignments_pkey;
ALTER TABLE IF EXISTS ONLY public.alembic_version DROP CONSTRAINT IF EXISTS alembic_version_pkc;
DROP TABLE IF EXISTS public.workflow_transitions;
DROP TABLE IF EXISTS public.workflow_steps;
DROP TABLE IF EXISTS public.workflow_statuses;
DROP TABLE IF EXISTS public.workflow_instances;
DROP TABLE IF EXISTS public.workflow_instance_steps;
DROP TABLE IF EXISTS public.workflow_history;
DROP TABLE IF EXISTS public.workflow_definitions;
DROP TABLE IF EXISTS public.workflow_assignment_rules;
DROP TABLE IF EXISTS public.workflow_actions;
DROP TABLE IF EXISTS public.vlr_workflow_step_history;
DROP TABLE IF EXISTS public.vlr_vendors;
DROP TABLE IF EXISTS public.vlr_vendor_contacts;
DROP TABLE IF EXISTS public.vlr_sla_configurations;
DROP TABLE IF EXISTS public.vlr_settings;
DROP TABLE IF EXISTS public.vlr_resolution_records;
DROP TABLE IF EXISTS public.vlr_recovery_items;
DROP TABLE IF EXISTS public.vlr_recovery_follow_ups;
DROP TABLE IF EXISTS public.vlr_reconciliation_requests;
DROP TABLE IF EXISTS public.vlr_reconciliation_cases;
DROP TABLE IF EXISTS public.vlr_reco_exceptions;
DROP TABLE IF EXISTS public.vlr_portal_sign_offs;
DROP TABLE IF EXISTS public.vlr_notifications;
DROP TABLE IF EXISTS public.vlr_match_results;
DROP TABLE IF EXISTS public.vlr_ledger_entries;
DROP TABLE IF EXISTS public.vlr_document_type_mappings;
DROP TABLE IF EXISTS public.vlr_column_mapping_templates;
DROP TABLE IF EXISTS public.vlr_automation_rules;
DROP TABLE IF EXISTS public.vlr_automation_executions;
DROP TABLE IF EXISTS public.vlr_audit_events;
DROP TABLE IF EXISTS public.vlr_approval_records;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.user_details;
DROP TABLE IF EXISTS public.tenants;
DROP SEQUENCE IF EXISTS public.taskset_id_sequence;
DROP SEQUENCE IF EXISTS public.task_id_sequence;
DROP TABLE IF EXISTS public.roles;
DROP TABLE IF EXISTS public.role_permissions;
DROP TABLE IF EXISTS public.role_assignments;
DROP SEQUENCE IF EXISTS public.queue_id_sequence;
DROP TABLE IF EXISTS public.permissions;
DROP SEQUENCE IF EXISTS public.message_id_sequence;
DROP TABLE IF EXISTS public.kombu_queue;
DROP TABLE IF EXISTS public.kombu_message;
DROP TABLE IF EXISTS public.commission_claims;
DROP TABLE IF EXISTS public.celery_tasksetmeta;
DROP TABLE IF EXISTS public.celery_taskmeta;
DROP TABLE IF EXISTS public.audit_logs;
DROP TABLE IF EXISTS public.approval_tasks;
DROP TABLE IF EXISTS public.approval_rules;
DROP TABLE IF EXISTS public.approval_matrices;
DROP TABLE IF EXISTS public.approval_delegations;
DROP TABLE IF EXISTS public.approval_conditions;
DROP TABLE IF EXISTS public.approval_assignments;
DROP TABLE IF EXISTS public.alembic_version;
DROP EXTENSION IF EXISTS btree_gist;
--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: approval_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_assignments (
    id uuid NOT NULL,
    matrix_id uuid NOT NULL,
    assignment_type character varying(20) NOT NULL,
    user_id uuid,
    role_id uuid,
    level integer DEFAULT 1 NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: approval_conditions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_conditions (
    id uuid NOT NULL,
    matrix_id uuid NOT NULL,
    condition_type character varying(50) NOT NULL,
    expression text NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: approval_delegations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_delegations (
    id uuid NOT NULL,
    delegator_id uuid NOT NULL,
    delegate_id uuid NOT NULL,
    from_date timestamp with time zone NOT NULL,
    to_date timestamp with time zone NOT NULL,
    entity_type character varying(100),
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: approval_matrices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_matrices (
    id uuid NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    entity_type character varying(100) NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: approval_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_rules (
    id uuid NOT NULL,
    matrix_id uuid NOT NULL,
    field character varying(100) NOT NULL,
    operator character varying(20) NOT NULL,
    value character varying(500) NOT NULL,
    data_type character varying(20) DEFAULT 'STRING'::character varying NOT NULL,
    logical_group character varying(50) DEFAULT 'default'::character varying NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: approval_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_tasks (
    id uuid NOT NULL,
    instance_id uuid NOT NULL,
    matrix_id uuid,
    assignee_id uuid NOT NULL,
    level integer DEFAULT 1 NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    action_taken character varying(50),
    due_date timestamp with time zone,
    comments text,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    actor_id uuid,
    actor_username character varying(255) NOT NULL,
    action character varying(50) NOT NULL,
    resource_type character varying(100) NOT NULL,
    resource_id character varying(100) DEFAULT ''::character varying NOT NULL,
    tenant_id uuid,
    old_value text,
    new_value text,
    ip_address character varying(45) DEFAULT ''::character varying NOT NULL,
    user_agent character varying(512) DEFAULT ''::character varying NOT NULL,
    extra_data text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: celery_taskmeta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.celery_taskmeta (
    id integer NOT NULL,
    task_id character varying(155),
    status character varying(50),
    result bytea,
    date_done timestamp without time zone,
    traceback text,
    name character varying(155),
    args bytea,
    kwargs bytea,
    worker character varying(155),
    retries integer,
    queue character varying(155)
);


--
-- Name: celery_tasksetmeta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.celery_tasksetmeta (
    id integer NOT NULL,
    taskset_id character varying(155),
    result bytea,
    date_done timestamp without time zone
);


--
-- Name: commission_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_claims (
    id uuid NOT NULL,
    claim_number character varying(50) NOT NULL,
    employee_id uuid NOT NULL,
    employee_name character varying(255) NOT NULL,
    amount numeric(12,2) NOT NULL,
    company character varying(100) NOT NULL,
    department character varying(100) DEFAULT ''::character varying NOT NULL,
    region character varying(100) DEFAULT ''::character varying NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    status character varying(30) DEFAULT 'DRAFT'::character varying NOT NULL,
    workflow_instance_id uuid,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kombu_message; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kombu_message (
    id integer NOT NULL,
    visible boolean,
    "timestamp" timestamp without time zone,
    payload text NOT NULL,
    version smallint NOT NULL,
    queue_id integer
);


--
-- Name: kombu_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kombu_queue (
    id integer NOT NULL,
    name character varying(200)
);


--
-- Name: message_id_sequence; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.message_id_sequence
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    id uuid NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    scope character varying(20) NOT NULL,
    resource character varying(255) NOT NULL,
    action character varying(20) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: queue_id_sequence; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.queue_id_sequence
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: role_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_assignments (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    role_id uuid NOT NULL,
    tenant_id uuid,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_permissions (
    id uuid NOT NULL,
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id uuid NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    is_system boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    tenant_id uuid,
    parent_role_id uuid,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: task_id_sequence; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_id_sequence
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: taskset_id_sequence; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.taskset_id_sequence
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id uuid NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    domain character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    settings text DEFAULT '{}'::text NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_details (
    user_id uuid NOT NULL,
    employee_id character varying(50) NOT NULL,
    employee_name character varying(255) NOT NULL,
    first_name character varying(255) NOT NULL,
    middle_name character varying(255) NOT NULL,
    last_name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    designation_title character varying(255) NOT NULL,
    department character varying(255) NOT NULL,
    business_unit character varying(255) NOT NULL,
    group_company character varying(255) NOT NULL,
    location character varying(255) NOT NULL,
    region character varying(255) NOT NULL,
    zone character varying(255) NOT NULL,
    grade character varying(50) NOT NULL,
    office_mobile_no character varying(50) NOT NULL,
    personal_mobile_no character varying(50) NOT NULL,
    date_of_joining character varying(50) NOT NULL,
    reporting_manager character varying(255) NOT NULL,
    direct_manager_employee_id character varying(50) NOT NULL,
    direct_manager_name character varying(255) NOT NULL,
    direct_manager_email character varying(255) NOT NULL,
    sap_user_id character varying(50) NOT NULL,
    division_id character varying(50) NOT NULL,
    territory_id character varying(50) NOT NULL,
    id uuid NOT NULL,
    created_by character varying(255) NOT NULL,
    created_date timestamp with time zone NOT NULL,
    modified_by character varying(255) NOT NULL,
    modified_date timestamp with time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    username character varying(255) NOT NULL,
    password_hash character varying(512) NOT NULL,
    is_active boolean NOT NULL,
    is_blocked boolean NOT NULL,
    id uuid NOT NULL,
    created_by character varying(255) NOT NULL,
    created_date timestamp with time zone NOT NULL,
    modified_by character varying(255) NOT NULL,
    modified_date timestamp with time zone NOT NULL,
    is_validate_ad boolean DEFAULT true NOT NULL
);


--
-- Name: vlr_approval_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_approval_records (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    decision character varying(30) NOT NULL,
    comments text,
    approver_id uuid NOT NULL,
    approval_level character varying(30) DEFAULT 'manager'::character varying NOT NULL,
    decision_date timestamp with time zone NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_audit_events (
    id uuid NOT NULL,
    actor_id uuid,
    actor_username character varying(100) NOT NULL,
    event_type character varying(50) NOT NULL,
    case_id uuid,
    event_details json DEFAULT '{}'::json NOT NULL,
    "timestamp" timestamp with time zone NOT NULL,
    ip_address character varying(45),
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE vlr_audit_events; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.vlr_audit_events IS 'Immutable audit trail. 7-year retention policy. No UPDATE/DELETE permitted.';


--
-- Name: COLUMN vlr_audit_events.actor_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events.actor_id IS 'User ID of the actor (null for system actions)';


--
-- Name: COLUMN vlr_audit_events.actor_username; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events.actor_username IS 'Username or identifier of the actor';


--
-- Name: COLUMN vlr_audit_events.event_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events.event_type IS 'Event type: login, logout, case_created, status_changed, match_override, approval, rejection, vendor_interaction';


--
-- Name: COLUMN vlr_audit_events.case_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events.case_id IS 'Associated reconciliation case ID (null for non-case events)';


--
-- Name: COLUMN vlr_audit_events.event_details; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events.event_details IS 'Structured JSON details about the event';


--
-- Name: COLUMN vlr_audit_events."timestamp"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events."timestamp" IS 'When the event occurred (UTC)';


--
-- Name: COLUMN vlr_audit_events.ip_address; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_audit_events.ip_address IS 'IP address of the actor (supports IPv6)';


--
-- Name: vlr_automation_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_automation_executions (
    id uuid NOT NULL,
    rule_id uuid NOT NULL,
    triggered_at timestamp with time zone NOT NULL,
    status character varying(20) NOT NULL,
    outcome text,
    error_details json,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_automation_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_automation_rules (
    id uuid NOT NULL,
    company_code character varying(20) NOT NULL,
    rule_type character varying(50) NOT NULL,
    frequency character varying(30) NOT NULL,
    configuration json,
    is_active boolean DEFAULT true NOT NULL,
    last_executed timestamp with time zone,
    next_execution timestamp with time zone,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_column_mapping_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_column_mapping_templates (
    id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    mapping_config json NOT NULL,
    created_by character varying(100) NOT NULL,
    last_used_at timestamp with time zone,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN vlr_column_mapping_templates.vendor_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_column_mapping_templates.vendor_id IS 'Reference to the vendor this template belongs to (one template per vendor)';


--
-- Name: COLUMN vlr_column_mapping_templates.mapping_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_column_mapping_templates.mapping_config IS 'Array of column mapping objects: [{column_index, header, tag, confidence}]';


--
-- Name: COLUMN vlr_column_mapping_templates.created_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_column_mapping_templates.created_by IS 'User who created or last updated this template';


--
-- Name: COLUMN vlr_column_mapping_templates.last_used_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_column_mapping_templates.last_used_at IS 'Timestamp of last time this template was applied to an upload';


--
-- Name: vlr_document_type_mappings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_document_type_mappings (
    id uuid NOT NULL,
    document_type_code character varying(10) NOT NULL,
    category character varying(30) NOT NULL,
    is_tds boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN vlr_document_type_mappings.document_type_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_document_type_mappings.document_type_code IS 'SAP document type code (e.g., RE, KR, DR, ZP, KZ, ZV, KG, RV)';


--
-- Name: COLUMN vlr_document_type_mappings.category; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_document_type_mappings.category IS 'Classification category: Invoice, Payment, Credit Note, Debit Note, TDS, Other';


--
-- Name: COLUMN vlr_document_type_mappings.is_tds; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_document_type_mappings.is_tds IS 'Whether this document type is a TDS entry';


--
-- Name: COLUMN vlr_document_type_mappings.is_active; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_document_type_mappings.is_active IS 'Whether this mapping is active (allows soft-delete)';


--
-- Name: vlr_ledger_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_ledger_entries (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    side character varying(10) NOT NULL,
    document_number character varying(50) NOT NULL,
    document_type character varying(20),
    reference_number character varying(100),
    posting_date date NOT NULL,
    clearing_date date,
    clearing_document character varying(50),
    amount numeric(15,2) NOT NULL,
    currency character varying(10) DEFAULT 'INR'::character varying NOT NULL,
    assignment_number character varying(100),
    description text,
    match_id uuid,
    pass_number integer,
    confidence_score numeric(5,4),
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    raw_reference character varying(255),
    derived_invoice_number character varying(255),
    invoice_source_field character varying(10),
    original_amount numeric(15,2),
    shkzg_indicator character varying(1),
    adjusted_amount numeric(15,2),
    transaction_currency character varying(10),
    local_currency_amount numeric(15,2),
    document_category character varying(30),
    is_tds boolean DEFAULT false NOT NULL,
    tds_parent_entry_id uuid,
    raw_data json
);


--
-- Name: COLUMN vlr_ledger_entries.raw_reference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.raw_reference IS 'Original source value before CLEAN';


--
-- Name: COLUMN vlr_ledger_entries.derived_invoice_number; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.derived_invoice_number IS 'After CLEAN function';


--
-- Name: COLUMN vlr_ledger_entries.invoice_source_field; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.invoice_source_field IS 'ZUONR, XBLNR, or BELNR';


--
-- Name: COLUMN vlr_ledger_entries.original_amount; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.original_amount IS 'Unsigned amount before sign adjustment';


--
-- Name: COLUMN vlr_ledger_entries.shkzg_indicator; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.shkzg_indicator IS 'H or S';


--
-- Name: COLUMN vlr_ledger_entries.adjusted_amount; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.adjusted_amount IS 'Signed amount after SHKZG adjustment';


--
-- Name: COLUMN vlr_ledger_entries.transaction_currency; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.transaction_currency IS 'Original transaction currency code';


--
-- Name: COLUMN vlr_ledger_entries.local_currency_amount; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.local_currency_amount IS 'INR equivalent amount';


--
-- Name: COLUMN vlr_ledger_entries.document_category; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.document_category IS 'Invoice, Payment, Credit Note, etc.';


--
-- Name: COLUMN vlr_ledger_entries.is_tds; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.is_tds IS 'TDS tag';


--
-- Name: COLUMN vlr_ledger_entries.tds_parent_entry_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_ledger_entries.tds_parent_entry_id IS 'Link to parent invoice entry';


--
-- Name: vlr_match_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_match_results (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    pass_number integer NOT NULL,
    match_type character varying(30) NOT NULL,
    confidence_score numeric(5,4) NOT NULL,
    is_confirmed boolean DEFAULT false NOT NULL,
    company_entry_ids json,
    vendor_entry_ids json,
    matched_amount numeric(15,2) NOT NULL,
    difference_amount numeric(15,2),
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_notifications (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    type character varying(30) NOT NULL,
    recipient_email character varying(255) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    template_code character varying(50),
    context_data json,
    sent_date timestamp with time zone,
    next_retry_date timestamp with time zone,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_portal_sign_offs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_portal_sign_offs (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    ip_address character varying(45) NOT NULL,
    statement_version character varying(50) NOT NULL,
    signed_at timestamp with time zone NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    confirmation_text text
);


--
-- Name: vlr_reco_exceptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_reco_exceptions (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    ledger_entry_id uuid NOT NULL,
    category character varying(50) NOT NULL,
    severity character varying(20) NOT NULL,
    amount numeric(15,2) NOT NULL,
    first_flagged_date date NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vlr_exception_valid_severity CHECK (((severity)::text = ANY ((ARRAY['critical'::character varying, 'high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: vlr_reconciliation_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_reconciliation_cases (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    case_type character varying(20) DEFAULT 'batch'::character varying NOT NULL,
    status character varying(30) DEFAULT 'created'::character varying NOT NULL,
    portal_token character varying(255),
    token_expiry timestamp with time zone,
    upload_count integer DEFAULT 0 NOT NULL,
    edit_count integer DEFAULT 0 NOT NULL,
    row_10_balance numeric(15,2),
    match_statistics json,
    is_deleted boolean DEFAULT false NOT NULL,
    deleted_at timestamp with time zone,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    current_workflow_step character varying(30),
    step_entered_at timestamp with time zone,
    sla_deadline timestamp with time zone,
    is_overdue boolean DEFAULT false NOT NULL,
    company_opening_balance numeric(15,2),
    company_closing_balance numeric(15,2),
    vendor_opening_balance numeric(15,2),
    vendor_closing_balance numeric(15,2),
    net_difference numeric(15,2),
    closure_type character varying(20),
    closure_justification text,
    closure_approved_by character varying(100),
    CONSTRAINT ck_vlr_case_valid_status CHECK (((status)::text = ANY ((ARRAY['created'::character varying, 'ledger_confirmed'::character varying, 'invited'::character varying, 'data_received'::character varying, 'matching'::character varying, 'matched'::character varying, 'review'::character varying, 'pending_approval'::character varying, 'approved'::character varying, 'signed_off'::character varying, 'closed'::character varying, 'mapping_pending'::character varying, 'statement_mapped'::character varying, 'in_progress'::character varying, 'auto_completed'::character varying, 'review_pending'::character varying, 'reviewed'::character varying, 'signoff_requested'::character varying, 'signoff_completed'::character varying, 'reco_rejected'::character varying])::text[]))),
    CONSTRAINT ck_vlr_case_valid_type CHECK (((case_type)::text = ANY ((ARRAY['batch'::character varying, 'direct'::character varying])::text[])))
);


--
-- Name: COLUMN vlr_reconciliation_cases.current_workflow_step; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.current_workflow_step IS 'Current step in the 10-step workflow';


--
-- Name: COLUMN vlr_reconciliation_cases.step_entered_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.step_entered_at IS 'Timestamp when the current workflow step was entered';


--
-- Name: COLUMN vlr_reconciliation_cases.sla_deadline; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.sla_deadline IS 'SLA deadline for the current workflow step';


--
-- Name: COLUMN vlr_reconciliation_cases.is_overdue; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.is_overdue IS 'Whether the current step has exceeded its SLA deadline';


--
-- Name: COLUMN vlr_reconciliation_cases.company_opening_balance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.company_opening_balance IS 'Company-side opening balance';


--
-- Name: COLUMN vlr_reconciliation_cases.company_closing_balance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.company_closing_balance IS 'Company-side closing balance';


--
-- Name: COLUMN vlr_reconciliation_cases.vendor_opening_balance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.vendor_opening_balance IS 'Vendor-side opening balance';


--
-- Name: COLUMN vlr_reconciliation_cases.vendor_closing_balance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.vendor_closing_balance IS 'Vendor-side closing balance';


--
-- Name: COLUMN vlr_reconciliation_cases.net_difference; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.net_difference IS 'Net difference between company and vendor';


--
-- Name: COLUMN vlr_reconciliation_cases.closure_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.closure_type IS 'Closure type: ''normal'' or ''one_sided''';


--
-- Name: COLUMN vlr_reconciliation_cases.closure_justification; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.closure_justification IS 'Justification text for one-sided closure';


--
-- Name: COLUMN vlr_reconciliation_cases.closure_approved_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_reconciliation_cases.closure_approved_by IS 'Recon_Manager who approved one-sided closure';


--
-- Name: vlr_reconciliation_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_reconciliation_requests (
    id uuid NOT NULL,
    company_code character varying(20) NOT NULL,
    fiscal_year character varying(10) NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    tolerance_amount numeric(15,2),
    tds_percentage numeric(5,2),
    gst_percentage numeric(5,2),
    matching_preferences json,
    description text,
    assigned_manager_id uuid,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vlr_request_valid_status CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'active'::character varying, 'in_progress'::character varying, 'review'::character varying, 'sign_off'::character varying, 'closed'::character varying])::text[])))
);


--
-- Name: vlr_recovery_follow_ups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_recovery_follow_ups (
    id uuid NOT NULL,
    recovery_item_id uuid NOT NULL,
    action_taken text NOT NULL,
    action_by character varying(100) NOT NULL,
    action_date timestamp with time zone NOT NULL,
    next_follow_up_date date,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN vlr_recovery_follow_ups.action_taken; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_follow_ups.action_taken IS 'Description of the follow-up action taken';


--
-- Name: COLUMN vlr_recovery_follow_ups.action_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_follow_ups.action_by IS 'User who performed the follow-up action';


--
-- Name: COLUMN vlr_recovery_follow_ups.action_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_follow_ups.action_date IS 'Timestamp when the action was performed';


--
-- Name: COLUMN vlr_recovery_follow_ups.next_follow_up_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_follow_ups.next_follow_up_date IS 'Scheduled date for the next follow-up';


--
-- Name: vlr_recovery_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_recovery_items (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    amount numeric(15,2) NOT NULL,
    currency character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    identified_date date NOT NULL,
    next_follow_up_date date,
    follow_up_interval_days integer DEFAULT 7 NOT NULL,
    notes text,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vlr_recovery_item_valid_status CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'in_progress'::character varying, 'recovered'::character varying, 'written_off'::character varying])::text[])))
);


--
-- Name: COLUMN vlr_recovery_items.amount; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.amount IS 'Recoverable amount';


--
-- Name: COLUMN vlr_recovery_items.currency; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.currency IS 'Currency code (default INR)';


--
-- Name: COLUMN vlr_recovery_items.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.status IS 'Recovery status: open, in_progress, recovered, written_off';


--
-- Name: COLUMN vlr_recovery_items.identified_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.identified_date IS 'Date the recovery item was identified';


--
-- Name: COLUMN vlr_recovery_items.next_follow_up_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.next_follow_up_date IS 'Next scheduled follow-up date';


--
-- Name: COLUMN vlr_recovery_items.follow_up_interval_days; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.follow_up_interval_days IS 'Days between follow-up reminders';


--
-- Name: COLUMN vlr_recovery_items.notes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_recovery_items.notes IS 'Additional notes about the recovery item';


--
-- Name: vlr_resolution_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_resolution_records (
    id uuid NOT NULL,
    exception_id uuid NOT NULL,
    action character varying(50) NOT NULL,
    comments text,
    resolved_by uuid NOT NULL,
    resolved_date timestamp with time zone NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vlr_resolution_valid_action CHECK (((action)::text = ANY ((ARRAY['accept_company_match'::character varying, 'request_document_vendor'::character varying, 'mark_tds_difference'::character varying, 'mark_agreed_adjustment'::character varying, 'write_off'::character varying, 'escalate'::character varying])::text[])))
);


--
-- Name: vlr_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_settings (
    id uuid NOT NULL,
    company_code character varying(20) NOT NULL,
    key character varying(100) NOT NULL,
    value text NOT NULL,
    value_type character varying(20) DEFAULT 'string'::character varying NOT NULL,
    description text,
    validation_rules json,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_sla_configurations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_sla_configurations (
    id uuid NOT NULL,
    step_name character varying(30) NOT NULL,
    sla_hours integer NOT NULL,
    escalation_email character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN vlr_sla_configurations.step_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_sla_configurations.step_name IS 'Workflow step name matching WorkflowStep enum values';


--
-- Name: COLUMN vlr_sla_configurations.sla_hours; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_sla_configurations.sla_hours IS 'Maximum allowed hours for this step before flagging as overdue';


--
-- Name: COLUMN vlr_sla_configurations.escalation_email; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_sla_configurations.escalation_email IS 'Email address for SLA violation escalation notifications';


--
-- Name: COLUMN vlr_sla_configurations.is_active; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_sla_configurations.is_active IS 'Whether this SLA configuration is active';


--
-- Name: vlr_vendor_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_vendor_contacts (
    id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(50),
    designation character varying(100),
    is_primary boolean DEFAULT false NOT NULL,
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_vendors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_vendors (
    id uuid NOT NULL,
    vendor_code character varying(50) NOT NULL,
    company_code character varying(20) NOT NULL,
    name character varying(255) NOT NULL,
    pan character varying(20),
    gstin character varying(20),
    city character varying(100),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    deleted_at timestamp with time zone,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vlr_workflow_step_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vlr_workflow_step_history (
    id uuid NOT NULL,
    case_id uuid NOT NULL,
    from_step character varying(30),
    to_step character varying(30) NOT NULL,
    triggered_by character varying(100) NOT NULL,
    triggered_at timestamp with time zone NOT NULL,
    sla_deadline timestamp with time zone,
    is_rollback boolean DEFAULT false NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN vlr_workflow_step_history.from_step; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_workflow_step_history.from_step IS 'Previous workflow step (null for initial transition)';


--
-- Name: COLUMN vlr_workflow_step_history.to_step; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_workflow_step_history.to_step IS 'Target workflow step';


--
-- Name: COLUMN vlr_workflow_step_history.triggered_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_workflow_step_history.triggered_by IS 'User or system that triggered the transition';


--
-- Name: COLUMN vlr_workflow_step_history.triggered_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_workflow_step_history.triggered_at IS 'Timestamp when the transition occurred';


--
-- Name: COLUMN vlr_workflow_step_history.sla_deadline; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_workflow_step_history.sla_deadline IS 'SLA deadline for the target step';


--
-- Name: COLUMN vlr_workflow_step_history.is_rollback; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.vlr_workflow_step_history.is_rollback IS 'Whether this transition is a rollback to a previous step';


--
-- Name: workflow_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_actions (
    id uuid NOT NULL,
    workflow_definition_id uuid NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    action_type character varying(20) NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_assignment_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_assignment_rules (
    id uuid NOT NULL,
    workflow_step_id uuid NOT NULL,
    assignment_type character varying(20) NOT NULL,
    role_id uuid,
    user_id uuid,
    matrix_rule_id uuid,
    expression text,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_definitions (
    id uuid NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    entity_type character varying(100) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_history (
    id uuid NOT NULL,
    instance_id uuid NOT NULL,
    from_status_id uuid,
    to_status_id uuid NOT NULL,
    action_code character varying(50) NOT NULL,
    actor_id uuid,
    actor_username character varying(255) DEFAULT ''::character varying NOT NULL,
    comments text DEFAULT ''::text NOT NULL,
    extra_data jsonb,
    ip_address character varying(45) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_instance_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_instance_steps (
    id uuid NOT NULL,
    instance_id uuid NOT NULL,
    step_id uuid NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    assigned_to_id uuid,
    assigned_at timestamp with time zone,
    completed_at timestamp with time zone,
    action_taken character varying(50),
    comments text,
    sla_due_at timestamp with time zone,
    is_escalated boolean DEFAULT false NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_instances (
    id uuid NOT NULL,
    workflow_definition_id uuid NOT NULL,
    entity_type character varying(100) NOT NULL,
    entity_id uuid NOT NULL,
    current_status_id uuid NOT NULL,
    initiated_by uuid NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    due_date timestamp with time zone,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    extra_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_statuses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_statuses (
    id uuid NOT NULL,
    workflow_definition_id uuid NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    is_initial boolean DEFAULT false NOT NULL,
    is_terminal boolean DEFAULT false NOT NULL,
    sequence integer DEFAULT 0 NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_steps (
    id uuid NOT NULL,
    workflow_definition_id uuid NOT NULL,
    from_status_id uuid NOT NULL,
    to_status_id uuid NOT NULL,
    action_code character varying(50) NOT NULL,
    step_type character varying(20) DEFAULT 'APPROVAL'::character varying NOT NULL,
    sequence integer DEFAULT 0 NOT NULL,
    is_parallel boolean DEFAULT false NOT NULL,
    sla_hours integer DEFAULT 0 NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_transitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_transitions (
    id uuid NOT NULL,
    workflow_definition_id uuid NOT NULL,
    from_status_id uuid NOT NULL,
    to_status_id uuid NOT NULL,
    action_code character varying(50) NOT NULL,
    guard_expression text,
    requires_comment boolean DEFAULT false NOT NULL,
    auto_execute boolean DEFAULT false NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    created_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    modified_by character varying(255) DEFAULT 'system'::character varying NOT NULL,
    modified_date timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: approval_assignments approval_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_assignments
    ADD CONSTRAINT approval_assignments_pkey PRIMARY KEY (id);


--
-- Name: approval_conditions approval_conditions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_conditions
    ADD CONSTRAINT approval_conditions_pkey PRIMARY KEY (id);


--
-- Name: approval_delegations approval_delegations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_delegations
    ADD CONSTRAINT approval_delegations_pkey PRIMARY KEY (id);


--
-- Name: approval_matrices approval_matrices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_matrices
    ADD CONSTRAINT approval_matrices_pkey PRIMARY KEY (id);


--
-- Name: approval_rules approval_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_rules
    ADD CONSTRAINT approval_rules_pkey PRIMARY KEY (id);


--
-- Name: approval_tasks approval_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_tasks
    ADD CONSTRAINT approval_tasks_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: celery_taskmeta celery_taskmeta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.celery_taskmeta
    ADD CONSTRAINT celery_taskmeta_pkey PRIMARY KEY (id);


--
-- Name: celery_taskmeta celery_taskmeta_task_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.celery_taskmeta
    ADD CONSTRAINT celery_taskmeta_task_id_key UNIQUE (task_id);


--
-- Name: celery_tasksetmeta celery_tasksetmeta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.celery_tasksetmeta
    ADD CONSTRAINT celery_tasksetmeta_pkey PRIMARY KEY (id);


--
-- Name: celery_tasksetmeta celery_tasksetmeta_taskset_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.celery_tasksetmeta
    ADD CONSTRAINT celery_tasksetmeta_taskset_id_key UNIQUE (taskset_id);


--
-- Name: commission_claims commission_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_claims
    ADD CONSTRAINT commission_claims_pkey PRIMARY KEY (id);


--
-- Name: kombu_message kombu_message_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kombu_message
    ADD CONSTRAINT kombu_message_pkey PRIMARY KEY (id);


--
-- Name: kombu_queue kombu_queue_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kombu_queue
    ADD CONSTRAINT kombu_queue_name_key UNIQUE (name);


--
-- Name: kombu_queue kombu_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kombu_queue
    ADD CONSTRAINT kombu_queue_pkey PRIMARY KEY (id);


--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);


--
-- Name: role_assignments role_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT role_assignments_pkey PRIMARY KEY (id);


--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: vlr_vendors uq_vendor_code_company_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_vendors
    ADD CONSTRAINT uq_vendor_code_company_code UNIQUE (vendor_code, company_code);


--
-- Name: user_details user_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_details
    ADD CONSTRAINT user_details_pkey PRIMARY KEY (id);


--
-- Name: user_details user_details_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_details
    ADD CONSTRAINT user_details_user_id_key UNIQUE (user_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vlr_approval_records vlr_approval_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_approval_records
    ADD CONSTRAINT vlr_approval_records_pkey PRIMARY KEY (id);


--
-- Name: vlr_audit_events vlr_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_audit_events
    ADD CONSTRAINT vlr_audit_events_pkey PRIMARY KEY (id);


--
-- Name: vlr_automation_executions vlr_automation_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_automation_executions
    ADD CONSTRAINT vlr_automation_executions_pkey PRIMARY KEY (id);


--
-- Name: vlr_automation_rules vlr_automation_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_automation_rules
    ADD CONSTRAINT vlr_automation_rules_pkey PRIMARY KEY (id);


--
-- Name: vlr_column_mapping_templates vlr_column_mapping_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_column_mapping_templates
    ADD CONSTRAINT vlr_column_mapping_templates_pkey PRIMARY KEY (id);


--
-- Name: vlr_column_mapping_templates vlr_column_mapping_templates_vendor_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_column_mapping_templates
    ADD CONSTRAINT vlr_column_mapping_templates_vendor_id_key UNIQUE (vendor_id);


--
-- Name: vlr_document_type_mappings vlr_document_type_mappings_document_type_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_document_type_mappings
    ADD CONSTRAINT vlr_document_type_mappings_document_type_code_key UNIQUE (document_type_code);


--
-- Name: vlr_document_type_mappings vlr_document_type_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_document_type_mappings
    ADD CONSTRAINT vlr_document_type_mappings_pkey PRIMARY KEY (id);


--
-- Name: vlr_ledger_entries vlr_ledger_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_ledger_entries
    ADD CONSTRAINT vlr_ledger_entries_pkey PRIMARY KEY (id);


--
-- Name: vlr_match_results vlr_match_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_match_results
    ADD CONSTRAINT vlr_match_results_pkey PRIMARY KEY (id);


--
-- Name: vlr_notifications vlr_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_notifications
    ADD CONSTRAINT vlr_notifications_pkey PRIMARY KEY (id);


--
-- Name: vlr_portal_sign_offs vlr_portal_sign_offs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_portal_sign_offs
    ADD CONSTRAINT vlr_portal_sign_offs_pkey PRIMARY KEY (id);


--
-- Name: vlr_reco_exceptions vlr_reco_exceptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reco_exceptions
    ADD CONSTRAINT vlr_reco_exceptions_pkey PRIMARY KEY (id);


--
-- Name: vlr_reconciliation_cases vlr_reconciliation_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reconciliation_cases
    ADD CONSTRAINT vlr_reconciliation_cases_pkey PRIMARY KEY (id);


--
-- Name: vlr_reconciliation_cases vlr_reconciliation_cases_portal_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reconciliation_cases
    ADD CONSTRAINT vlr_reconciliation_cases_portal_token_key UNIQUE (portal_token);


--
-- Name: vlr_reconciliation_requests vlr_reconciliation_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reconciliation_requests
    ADD CONSTRAINT vlr_reconciliation_requests_pkey PRIMARY KEY (id);


--
-- Name: vlr_recovery_follow_ups vlr_recovery_follow_ups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_recovery_follow_ups
    ADD CONSTRAINT vlr_recovery_follow_ups_pkey PRIMARY KEY (id);


--
-- Name: vlr_recovery_items vlr_recovery_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_recovery_items
    ADD CONSTRAINT vlr_recovery_items_pkey PRIMARY KEY (id);


--
-- Name: vlr_resolution_records vlr_resolution_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_resolution_records
    ADD CONSTRAINT vlr_resolution_records_pkey PRIMARY KEY (id);


--
-- Name: vlr_settings vlr_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_settings
    ADD CONSTRAINT vlr_settings_pkey PRIMARY KEY (id);


--
-- Name: vlr_sla_configurations vlr_sla_configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_sla_configurations
    ADD CONSTRAINT vlr_sla_configurations_pkey PRIMARY KEY (id);


--
-- Name: vlr_sla_configurations vlr_sla_configurations_step_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_sla_configurations
    ADD CONSTRAINT vlr_sla_configurations_step_name_key UNIQUE (step_name);


--
-- Name: vlr_vendor_contacts vlr_vendor_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_vendor_contacts
    ADD CONSTRAINT vlr_vendor_contacts_pkey PRIMARY KEY (id);


--
-- Name: vlr_vendors vlr_vendors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_vendors
    ADD CONSTRAINT vlr_vendors_pkey PRIMARY KEY (id);


--
-- Name: vlr_workflow_step_history vlr_workflow_step_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_workflow_step_history
    ADD CONSTRAINT vlr_workflow_step_history_pkey PRIMARY KEY (id);


--
-- Name: workflow_actions workflow_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_actions
    ADD CONSTRAINT workflow_actions_pkey PRIMARY KEY (id);


--
-- Name: workflow_assignment_rules workflow_assignment_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_assignment_rules
    ADD CONSTRAINT workflow_assignment_rules_pkey PRIMARY KEY (id);


--
-- Name: workflow_definitions workflow_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT workflow_definitions_pkey PRIMARY KEY (id);


--
-- Name: workflow_history workflow_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_history
    ADD CONSTRAINT workflow_history_pkey PRIMARY KEY (id);


--
-- Name: workflow_instance_steps workflow_instance_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_instance_steps
    ADD CONSTRAINT workflow_instance_steps_pkey PRIMARY KEY (id);


--
-- Name: workflow_instances workflow_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_instances
    ADD CONSTRAINT workflow_instances_pkey PRIMARY KEY (id);


--
-- Name: workflow_statuses workflow_statuses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_statuses
    ADD CONSTRAINT workflow_statuses_pkey PRIMARY KEY (id);


--
-- Name: workflow_steps workflow_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_steps
    ADD CONSTRAINT workflow_steps_pkey PRIMARY KEY (id);


--
-- Name: workflow_transitions workflow_transitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_transitions
    ADD CONSTRAINT workflow_transitions_pkey PRIMARY KEY (id);


--
-- Name: ix_approval_assignments_matrix_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_assignments_matrix_id ON public.approval_assignments USING btree (matrix_id);


--
-- Name: ix_approval_conditions_matrix_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_conditions_matrix_id ON public.approval_conditions USING btree (matrix_id);


--
-- Name: ix_approval_delegations_delegate_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_delegations_delegate_id ON public.approval_delegations USING btree (delegate_id);


--
-- Name: ix_approval_delegations_delegator_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_delegations_delegator_id ON public.approval_delegations USING btree (delegator_id);


--
-- Name: ix_approval_matrices_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_approval_matrices_code ON public.approval_matrices USING btree (code);


--
-- Name: ix_approval_matrices_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_matrices_entity_type ON public.approval_matrices USING btree (entity_type);


--
-- Name: ix_approval_rules_matrix_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_rules_matrix_id ON public.approval_rules USING btree (matrix_id);


--
-- Name: ix_approval_tasks_assignee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_tasks_assignee_id ON public.approval_tasks USING btree (assignee_id);


--
-- Name: ix_approval_tasks_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_tasks_instance_id ON public.approval_tasks USING btree (instance_id);


--
-- Name: ix_approval_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_tasks_status ON public.approval_tasks USING btree (status);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_actor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_actor_id ON public.audit_logs USING btree (actor_id);


--
-- Name: ix_audit_logs_actor_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_actor_username ON public.audit_logs USING btree (actor_username);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_audit_logs_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_type ON public.audit_logs USING btree (resource_type);


--
-- Name: ix_audit_logs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_tenant_id ON public.audit_logs USING btree (tenant_id);


--
-- Name: ix_celery_taskmeta_date_done; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_celery_taskmeta_date_done ON public.celery_taskmeta USING btree (date_done);


--
-- Name: ix_celery_tasksetmeta_date_done; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_celery_tasksetmeta_date_done ON public.celery_tasksetmeta USING btree (date_done);


--
-- Name: ix_commission_claims_claim_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_commission_claims_claim_number ON public.commission_claims USING btree (claim_number);


--
-- Name: ix_commission_claims_employee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_claims_employee_id ON public.commission_claims USING btree (employee_id);


--
-- Name: ix_commission_claims_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_claims_status ON public.commission_claims USING btree (status);


--
-- Name: ix_kombu_message_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kombu_message_timestamp ON public.kombu_message USING btree ("timestamp");


--
-- Name: ix_kombu_message_timestamp_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kombu_message_timestamp_id ON public.kombu_message USING btree ("timestamp", id);


--
-- Name: ix_kombu_message_visible; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kombu_message_visible ON public.kombu_message USING btree (visible);


--
-- Name: ix_permissions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_permissions_code ON public.permissions USING btree (code);


--
-- Name: ix_permissions_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_permissions_resource ON public.permissions USING btree (resource);


--
-- Name: ix_permissions_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_permissions_scope ON public.permissions USING btree (scope);


--
-- Name: ix_role_assignments_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignments_role_id ON public.role_assignments USING btree (role_id);


--
-- Name: ix_role_assignments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignments_tenant_id ON public.role_assignments USING btree (tenant_id);


--
-- Name: ix_role_assignments_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignments_user_id ON public.role_assignments USING btree (user_id);


--
-- Name: ix_role_permissions_permission_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_permissions_permission_id ON public.role_permissions USING btree (permission_id);


--
-- Name: ix_role_permissions_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_permissions_role_id ON public.role_permissions USING btree (role_id);


--
-- Name: ix_roles_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_roles_code ON public.roles USING btree (code);


--
-- Name: ix_roles_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roles_tenant_id ON public.roles USING btree (tenant_id);


--
-- Name: ix_tenants_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenants_code ON public.tenants USING btree (code);


--
-- Name: ix_tenants_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenants_domain ON public.tenants USING btree (domain);


--
-- Name: ix_user_details_employee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_details_employee_id ON public.user_details USING btree (employee_id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: ix_vlr_approval_records_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_approval_records_case_id ON public.vlr_approval_records USING btree (case_id);


--
-- Name: ix_vlr_audit_events_actor_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_audit_events_actor_username ON public.vlr_audit_events USING btree (actor_username);


--
-- Name: ix_vlr_audit_events_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_audit_events_case_id ON public.vlr_audit_events USING btree (case_id);


--
-- Name: ix_vlr_audit_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_audit_events_event_type ON public.vlr_audit_events USING btree (event_type);


--
-- Name: ix_vlr_audit_events_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_audit_events_timestamp ON public.vlr_audit_events USING btree ("timestamp");


--
-- Name: ix_vlr_audit_events_timestamp_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_audit_events_timestamp_event_type ON public.vlr_audit_events USING btree ("timestamp", event_type);


--
-- Name: ix_vlr_automation_executions_rule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_automation_executions_rule_id ON public.vlr_automation_executions USING btree (rule_id);


--
-- Name: ix_vlr_automation_rules_company_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_automation_rules_company_code ON public.vlr_automation_rules USING btree (company_code);


--
-- Name: ix_vlr_automation_rules_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_automation_rules_is_active ON public.vlr_automation_rules USING btree (is_active);


--
-- Name: ix_vlr_cases_created_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_cases_created_date ON public.vlr_reconciliation_cases USING btree (created_date);


--
-- Name: ix_vlr_cases_is_overdue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_cases_is_overdue ON public.vlr_reconciliation_cases USING btree (is_overdue);


--
-- Name: ix_vlr_cases_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_cases_request_id ON public.vlr_reconciliation_cases USING btree (request_id);


--
-- Name: ix_vlr_cases_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_cases_status ON public.vlr_reconciliation_cases USING btree (status);


--
-- Name: ix_vlr_cases_vendor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_cases_vendor_id ON public.vlr_reconciliation_cases USING btree (vendor_id);


--
-- Name: ix_vlr_cases_workflow_step; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_cases_workflow_step ON public.vlr_reconciliation_cases USING btree (current_workflow_step);


--
-- Name: ix_vlr_column_mapping_templates_vendor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_column_mapping_templates_vendor_id ON public.vlr_column_mapping_templates USING btree (vendor_id);


--
-- Name: ix_vlr_doc_type_mappings_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_doc_type_mappings_active ON public.vlr_document_type_mappings USING btree (is_active);


--
-- Name: ix_vlr_doc_type_mappings_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_doc_type_mappings_category ON public.vlr_document_type_mappings USING btree (category);


--
-- Name: ix_vlr_doc_type_mappings_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_doc_type_mappings_code ON public.vlr_document_type_mappings USING btree (document_type_code);


--
-- Name: ix_vlr_exceptions_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_exceptions_case_id ON public.vlr_reco_exceptions USING btree (case_id);


--
-- Name: ix_vlr_exceptions_ledger_entry_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_exceptions_ledger_entry_id ON public.vlr_reco_exceptions USING btree (ledger_entry_id);


--
-- Name: ix_vlr_exceptions_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_exceptions_severity ON public.vlr_reco_exceptions USING btree (severity);


--
-- Name: ix_vlr_exceptions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_exceptions_status ON public.vlr_reco_exceptions USING btree (status);


--
-- Name: ix_vlr_ledger_entries_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_ledger_entries_case_id ON public.vlr_ledger_entries USING btree (case_id);


--
-- Name: ix_vlr_ledger_entries_derived_invoice; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_ledger_entries_derived_invoice ON public.vlr_ledger_entries USING btree (derived_invoice_number);


--
-- Name: ix_vlr_ledger_entries_document_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_ledger_entries_document_number ON public.vlr_ledger_entries USING btree (document_number);


--
-- Name: ix_vlr_ledger_entries_is_tds; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_ledger_entries_is_tds ON public.vlr_ledger_entries USING btree (is_tds);


--
-- Name: ix_vlr_ledger_entries_match_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_ledger_entries_match_id ON public.vlr_ledger_entries USING btree (match_id);


--
-- Name: ix_vlr_ledger_entries_side; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_ledger_entries_side ON public.vlr_ledger_entries USING btree (side);


--
-- Name: ix_vlr_match_results_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_match_results_case_id ON public.vlr_match_results USING btree (case_id);


--
-- Name: ix_vlr_match_results_pass_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_match_results_pass_number ON public.vlr_match_results USING btree (pass_number);


--
-- Name: ix_vlr_notifications_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_notifications_case_id ON public.vlr_notifications USING btree (case_id);


--
-- Name: ix_vlr_notifications_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_notifications_status ON public.vlr_notifications USING btree (status);


--
-- Name: ix_vlr_notifications_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_notifications_type ON public.vlr_notifications USING btree (type);


--
-- Name: ix_vlr_portal_sign_offs_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_portal_sign_offs_case_id ON public.vlr_portal_sign_offs USING btree (case_id);


--
-- Name: ix_vlr_recovery_follow_ups_item_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_recovery_follow_ups_item_date ON public.vlr_recovery_follow_ups USING btree (recovery_item_id, action_date);


--
-- Name: ix_vlr_recovery_follow_ups_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_recovery_follow_ups_item_id ON public.vlr_recovery_follow_ups USING btree (recovery_item_id);


--
-- Name: ix_vlr_recovery_items_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_recovery_items_case_id ON public.vlr_recovery_items USING btree (case_id);


--
-- Name: ix_vlr_recovery_items_next_follow_up; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_recovery_items_next_follow_up ON public.vlr_recovery_items USING btree (next_follow_up_date);


--
-- Name: ix_vlr_recovery_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_recovery_items_status ON public.vlr_recovery_items USING btree (status);


--
-- Name: ix_vlr_recovery_items_vendor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_recovery_items_vendor_id ON public.vlr_recovery_items USING btree (vendor_id);


--
-- Name: ix_vlr_requests_company_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_requests_company_code ON public.vlr_reconciliation_requests USING btree (company_code);


--
-- Name: ix_vlr_requests_created_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_requests_created_date ON public.vlr_reconciliation_requests USING btree (created_date);


--
-- Name: ix_vlr_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_requests_status ON public.vlr_reconciliation_requests USING btree (status);


--
-- Name: ix_vlr_resolution_records_exception_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_resolution_records_exception_id ON public.vlr_resolution_records USING btree (exception_id);


--
-- Name: ix_vlr_settings_company_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_settings_company_code ON public.vlr_settings USING btree (company_code);


--
-- Name: ix_vlr_settings_company_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_vlr_settings_company_key ON public.vlr_settings USING btree (company_code, key);


--
-- Name: ix_vlr_settings_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_settings_key ON public.vlr_settings USING btree (key);


--
-- Name: ix_vlr_sla_config_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_sla_config_active ON public.vlr_sla_configurations USING btree (is_active);


--
-- Name: ix_vlr_sla_config_step; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_sla_config_step ON public.vlr_sla_configurations USING btree (step_name);


--
-- Name: ix_vlr_vendor_contacts_vendor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_vendor_contacts_vendor_id ON public.vlr_vendor_contacts USING btree (vendor_id);


--
-- Name: ix_vlr_vendors_company_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_vendors_company_code ON public.vlr_vendors USING btree (company_code);


--
-- Name: ix_vlr_vendors_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_vendors_status ON public.vlr_vendors USING btree (status);


--
-- Name: ix_vlr_vendors_vendor_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_vendors_vendor_code ON public.vlr_vendors USING btree (vendor_code);


--
-- Name: ix_vlr_wf_history_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_wf_history_case_id ON public.vlr_workflow_step_history USING btree (case_id);


--
-- Name: ix_vlr_wf_history_case_triggered; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_wf_history_case_triggered ON public.vlr_workflow_step_history USING btree (case_id, triggered_at);


--
-- Name: ix_vlr_wf_history_to_step; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vlr_wf_history_to_step ON public.vlr_workflow_step_history USING btree (to_step);


--
-- Name: ix_workflow_actions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_actions_code ON public.workflow_actions USING btree (code);


--
-- Name: ix_workflow_actions_workflow_definition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_actions_workflow_definition_id ON public.workflow_actions USING btree (workflow_definition_id);


--
-- Name: ix_workflow_assignment_rules_workflow_step_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_assignment_rules_workflow_step_id ON public.workflow_assignment_rules USING btree (workflow_step_id);


--
-- Name: ix_workflow_definitions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_workflow_definitions_code ON public.workflow_definitions USING btree (code);


--
-- Name: ix_workflow_definitions_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_definitions_entity_type ON public.workflow_definitions USING btree (entity_type);


--
-- Name: ix_workflow_history_action_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_history_action_code ON public.workflow_history USING btree (action_code);


--
-- Name: ix_workflow_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_history_created_at ON public.workflow_history USING btree (created_at);


--
-- Name: ix_workflow_history_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_history_instance_id ON public.workflow_history USING btree (instance_id);


--
-- Name: ix_workflow_instance_steps_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instance_steps_instance_id ON public.workflow_instance_steps USING btree (instance_id);


--
-- Name: ix_workflow_instances_current_status_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instances_current_status_id ON public.workflow_instances USING btree (current_status_id);


--
-- Name: ix_workflow_instances_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instances_entity_id ON public.workflow_instances USING btree (entity_id);


--
-- Name: ix_workflow_instances_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instances_entity_type ON public.workflow_instances USING btree (entity_type);


--
-- Name: ix_workflow_instances_workflow_definition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instances_workflow_definition_id ON public.workflow_instances USING btree (workflow_definition_id);


--
-- Name: ix_workflow_statuses_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_statuses_code ON public.workflow_statuses USING btree (code);


--
-- Name: ix_workflow_statuses_workflow_definition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_statuses_workflow_definition_id ON public.workflow_statuses USING btree (workflow_definition_id);


--
-- Name: ix_workflow_steps_workflow_definition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_steps_workflow_definition_id ON public.workflow_steps USING btree (workflow_definition_id);


--
-- Name: ix_workflow_transitions_action_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_transitions_action_code ON public.workflow_transitions USING btree (action_code);


--
-- Name: ix_workflow_transitions_from_status_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_transitions_from_status_id ON public.workflow_transitions USING btree (from_status_id);


--
-- Name: ix_workflow_transitions_workflow_definition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_transitions_workflow_definition_id ON public.workflow_transitions USING btree (workflow_definition_id);


--
-- Name: uq_vlr_cases_vendor_request; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_vlr_cases_vendor_request ON public.vlr_reconciliation_cases USING btree (vendor_id, request_id) WHERE (is_deleted = false);


--
-- Name: kombu_message FK_kombu_message_queue; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kombu_message
    ADD CONSTRAINT "FK_kombu_message_queue" FOREIGN KEY (queue_id) REFERENCES public.kombu_queue(id);


--
-- Name: role_assignments role_assignments_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT role_assignments_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: role_assignments role_assignments_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT role_assignments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE SET NULL;


--
-- Name: role_assignments role_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT role_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: roles roles_parent_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_parent_role_id_fkey FOREIGN KEY (parent_role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: roles roles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE SET NULL;


--
-- Name: user_details user_details_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_details
    ADD CONSTRAINT user_details_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: vlr_approval_records vlr_approval_records_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_approval_records
    ADD CONSTRAINT vlr_approval_records_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_automation_executions vlr_automation_executions_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_automation_executions
    ADD CONSTRAINT vlr_automation_executions_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.vlr_automation_rules(id) ON DELETE CASCADE;


--
-- Name: vlr_column_mapping_templates vlr_column_mapping_templates_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_column_mapping_templates
    ADD CONSTRAINT vlr_column_mapping_templates_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vlr_vendors(id);


--
-- Name: vlr_ledger_entries vlr_ledger_entries_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_ledger_entries
    ADD CONSTRAINT vlr_ledger_entries_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_match_results vlr_match_results_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_match_results
    ADD CONSTRAINT vlr_match_results_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_notifications vlr_notifications_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_notifications
    ADD CONSTRAINT vlr_notifications_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_portal_sign_offs vlr_portal_sign_offs_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_portal_sign_offs
    ADD CONSTRAINT vlr_portal_sign_offs_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_reco_exceptions vlr_reco_exceptions_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reco_exceptions
    ADD CONSTRAINT vlr_reco_exceptions_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_reco_exceptions vlr_reco_exceptions_ledger_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reco_exceptions
    ADD CONSTRAINT vlr_reco_exceptions_ledger_entry_id_fkey FOREIGN KEY (ledger_entry_id) REFERENCES public.vlr_ledger_entries(id) ON DELETE CASCADE;


--
-- Name: vlr_reconciliation_cases vlr_reconciliation_cases_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reconciliation_cases
    ADD CONSTRAINT vlr_reconciliation_cases_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.vlr_reconciliation_requests(id) ON DELETE CASCADE;


--
-- Name: vlr_reconciliation_cases vlr_reconciliation_cases_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_reconciliation_cases
    ADD CONSTRAINT vlr_reconciliation_cases_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vlr_vendors(id) ON DELETE RESTRICT;


--
-- Name: vlr_recovery_follow_ups vlr_recovery_follow_ups_recovery_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_recovery_follow_ups
    ADD CONSTRAINT vlr_recovery_follow_ups_recovery_item_id_fkey FOREIGN KEY (recovery_item_id) REFERENCES public.vlr_recovery_items(id) ON DELETE CASCADE;


--
-- Name: vlr_recovery_items vlr_recovery_items_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_recovery_items
    ADD CONSTRAINT vlr_recovery_items_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- Name: vlr_recovery_items vlr_recovery_items_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_recovery_items
    ADD CONSTRAINT vlr_recovery_items_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vlr_vendors(id) ON DELETE RESTRICT;


--
-- Name: vlr_resolution_records vlr_resolution_records_exception_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_resolution_records
    ADD CONSTRAINT vlr_resolution_records_exception_id_fkey FOREIGN KEY (exception_id) REFERENCES public.vlr_reco_exceptions(id) ON DELETE CASCADE;


--
-- Name: vlr_vendor_contacts vlr_vendor_contacts_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_vendor_contacts
    ADD CONSTRAINT vlr_vendor_contacts_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vlr_vendors(id) ON DELETE CASCADE;


--
-- Name: vlr_workflow_step_history vlr_workflow_step_history_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vlr_workflow_step_history
    ADD CONSTRAINT vlr_workflow_step_history_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

