export type Role = 'active' | 'passive' | 'unknown'
export type AccessRole = 'reader' | 'operator' | 'full_control'

export interface Session {
  actor: string
  display_name: string
  user_id: string | null
  role: AccessRole
  identity_type: 'person' | 'api'
  two_factor_enabled: boolean
  password_change_required: boolean
  csrf_token: string
  expires_at: string | null
  method: string
}

export interface UserProfile {
  id: string
  username: string
  display_name: string
  role: string
  status: string
  two_factor_enabled: boolean
  two_factor_pending: boolean
  recovery_codes_remaining: number
  password_change_required: boolean
  password_changed_at: string
  created_at: string
  updated_at: string
  password_policy: { minimum_length: number; maximum_length: number }
}

export interface ManagedUser {
  id: string
  username: string
  display_name: string
  role: AccessRole
  identity_type: 'person'
  status: 'active' | 'disabled'
  two_factor_enabled: boolean
  password_change_required: boolean
  password_changed_at: string
  created_at: string
  updated_at: string
}

export interface ApiClient {
  id: string
  name: string
  description: string
  role: AccessRole
  identity_type: 'api'
  status: 'active' | 'disabled' | 'revoked'
  token_prefix: string
  expires_at: string | null
  expired: boolean
  last_used_at: string | null
  last_used_ip: string | null
  created_at: string
  updated_at: string
}

export interface Version { clock: number; timestamp: string; node: string }

export interface Library {
  id: string
  name: string
  slug: string
  description: string
  icon: string
  color: string
  position: number
  category_sort?: 'manual' | 'alphabetical'
  access_mode: 'open' | 'restricted'
  effective_role: AccessRole
  status: string
  updated_at: string
  updated_by: string
  counts?: { categories: number; documents: number }
}

export interface Category {
  id: string
  library_id: string
  parent_id: string | null
  name: string
  description: string
  position: number
  status: string
  type?: 'category'
  children: Category[]
  documents: DocumentMeta[]
}

export interface DocumentMeta {
  id: string
  library_id: string | null
  category_id: string | null
  title: string
  slug: string
  summary: string
  tags: string[]
  position: number
  status: 'active' | 'archived' | 'deleted'
  created_at: string
  updated_at: string
  updated_by: string
  version: Version
  effective_role: AccessRole
  type?: 'document'
}

export interface LibraryPermissionGrant {
  subject_type: 'user' | 'api_client'
  subject_id: string
  role: AccessRole
}

export interface LibraryPermissionSubject {
  id: string
  identity_type: 'person' | 'api'
  username?: string
  display_name?: string
  name?: string
  description?: string
  role: AccessRole
  status: string
}

export interface LibraryPermissions {
  library: Library
  mode: 'open' | 'restricted'
  grants: LibraryPermissionGrant[]
  subjects: LibraryPermissionSubject[]
}

export interface FavoriteDocument extends DocumentMeta { favorited_at: string }

export interface DocumentImage {
  id: string
  document_id: string
  filename: string
  media_type: string
  size: number
  created_at: string
  created_by: string
  url: string
}

export interface DocumentRecord { meta: DocumentMeta; content: string | null; images: DocumentImage[] }
export interface LibraryTree { library: Library; categories: Category[]; documents: DocumentMeta[] }

export interface AuditEvent {
  event_id: string
  operation_id: string
  timestamp: string
  level: string
  source: string
  actor: string
  node: string
  action: string
  result: string
  entity_type?: string
  entity_id?: string
  before?: unknown
  after?: unknown
}

export interface PublicSystemStatus {
  setup_required: boolean
  node: string
  role: Role
  role_reason: string
  active_url: string | null
  floating_ip_connector: {
    state: 'ok' | 'degraded' | 'unknown' | 'manual' | 'disabled'
    error: string | null
  }
  sync_interval_seconds: number
  version: string
}

export interface SystemStatus {
  setup_required: boolean
  node: string
  role: Role
  role_reason: string
  owns_floating_ip: boolean | null
  floating_ip: string | null
  floating_url: string | null
  active_url: string | null
  floating_ip_connector: {
    configured: boolean
    state: 'ok' | 'degraded' | 'unknown' | 'manual' | 'disabled'
    source: 'keepalived' | 'manual' | null
    api_url: string | null
    service: string
    claim_id: string
    ip: string | null
    last_attempt_at: string | null
    last_success_at: string | null
    error: string | null
  }
  retention_days: number
  sync_interval_seconds: number
  max_image_size_mb: number
  sync: {
    clock: number
    last_sync_at: string | null
    peers: Record<string, { ok?: boolean; at?: string; error?: string }>
    documents: number
    active_documents: number
  }
  peers_configured: string[]
  git: { enabled: boolean; ready: boolean; clean?: boolean; head?: string; error?: string }
  version: string
}

export interface SystemConfigurationValues {
  node: string
  role_mode: 'auto' | 'active' | 'passive' | 'unknown'
  public: {
    scheme: 'http' | 'https'
    forwarded_allow_ips: string
    floating_ip: string
    floating_url: string
    session_cookie_secure: boolean
  }
  keepalived: {
    url: string
    api_key: string
    service: string
    description: string
    claim_id: string
    health_path: string
    service_ports: number[]
    timeout_seconds: number
    allow_insecure_http: boolean
    ca_pem: string
  }
  replication: {
    peers: Array<{ name: string; url: string }>
    allow_insecure_http: boolean
    ca_pem: string
    max_mb: number
  }
  policy: {
    retention_days: number
    sync_interval_seconds: number
    max_image_size_mb: number
    session_hours: number
    login_max_attempts: number
    login_window_seconds: number
    password_min_length: number
    totp_issuer: string
  }
  git: { enabled: boolean; author_name: string; author_email: string }
}

export interface SystemConfiguration {
  values: SystemConfigurationValues
  secrets: { keepalived_api_key_configured: boolean }
}
