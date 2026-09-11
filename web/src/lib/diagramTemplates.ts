export interface DiagramTemplate {
  id: string
  name: string
  description: string
  code: string
}

export const diagramTemplates: DiagramTemplate[] = [
  {
    id: 'flowchart',
    name: 'Flujo de proceso',
    description: 'Decisiones, pasos, automatizaciones y procedimientos.',
    code: `flowchart LR
    A["Inicio"] --> B["Procesar solicitud"]
    B --> C{"¿Resultado correcto?"}
    C -- Sí --> D["Publicar cambio"]
    C -- No --> E["Revisar incidencia"]
    E --> B
    D --> F(["Fin"])`,
  },
  {
    id: 'infrastructure',
    name: 'Arquitectura técnica',
    description: 'Servicios, nodos, redes, almacenamiento y dependencias.',
    code: `flowchart TB
    Client["Usuarios y aplicaciones"] --> VIP["IP flotante"]
    subgraph Cluster["Clúster documental"]
        Active["Nodo activo"]
        PassiveA["Nodo pasivo A"]
        PassiveB["Nodo pasivo B"]
    end
    VIP --> Active
    Active -->|"Réplica"| PassiveA
    Active -->|"Réplica"| PassiveB
    Active --> Storage[("Datos persistentes")]`,
  },
  {
    id: 'sequence',
    name: 'Secuencia',
    description: 'Interacciones temporales entre usuarios, APIs y servicios.',
    code: `sequenceDiagram
    autonumber
    actor Usuario
    participant Portal
    participant API
    participant Datos
    Usuario->>Portal: Ejecuta una operación
    Portal->>API: Solicitud autenticada
    API->>Datos: Valida y persiste
    Datos-->>API: Operación registrada
    API-->>Portal: Resultado
    Portal-->>Usuario: Confirmación`,
  },
  {
    id: 'state',
    name: 'Estados',
    description: 'Ciclos de vida, estados operativos y transiciones.',
    code: `stateDiagram-v2
    [*] --> Borrador
    Borrador --> Vigente: publicar
    Vigente --> Archivado: archivar
    Archivado --> Vigente: reactivar
    Vigente --> Papelera: eliminar
    Papelera --> Vigente: restaurar
    Papelera --> [*]: finalizar retención`,
  },
  {
    id: 'er',
    name: 'Entidad–relación',
    description: 'Modelos de datos y relaciones entre entidades.',
    code: `erDiagram
    BIBLIOTECA ||--o{ CATEGORIA : contiene
    BIBLIOTECA ||--o{ DOCUMENTO : organiza
    CATEGORIA ||--o{ CATEGORIA : anida
    CATEGORIA ||--o{ DOCUMENTO : clasifica
    DOCUMENTO }o--o{ ETIQUETA : utiliza
    DOCUMENTO {
        string id
        string titulo
        string estado
    }`,
  },
  {
    id: 'class',
    name: 'Clases y componentes',
    description: 'Responsabilidades, interfaces y dependencias de código.',
    code: `classDiagram
    class ServicioDocumental {
        +crearDocumento()
        +actualizarDocumento()
        +replicar()
    }
    class Repositorio {
        +guardar()
        +obtener()
    }
    class Auditoria {
        +registrarOperacion()
    }
    ServicioDocumental --> Repositorio
    ServicioDocumental --> Auditoria`,
  },
  {
    id: 'gantt',
    name: 'Planificación Gantt',
    description: 'Fases, dependencias, hitos y calendarios.',
    code: `gantt
    title Plan de implementación
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section Preparación
    Diseño técnico        :done, design, 2026-08-21, 3d
    section Construcción
    Implementación        :active, build, after design, 5d
    Validación            :test, after build, 3d
    section Entrega
    Despliegue            :milestone, after test, 0d`,
  },
  {
    id: 'mindmap',
    name: 'Mapa mental',
    description: 'Ideas, áreas funcionales y jerarquías conceptuales.',
    code: `mindmap
  root((Proyecto))
    Infraestructura
      Servidores
      Redes
      Almacenamiento
    Aplicación
      Frontend
      API
      Datos
    Operación
      Monitorización
      Copias
      Procedimientos`,
  },
  {
    id: 'pie',
    name: 'Gráfico circular',
    description: 'Distribuciones sencillas y proporciones.',
    code: `pie showData
    title Distribución de servicios
    "Producción" : 55
    "Pruebas" : 25
    "Infraestructura" : 20`,
  },
]
