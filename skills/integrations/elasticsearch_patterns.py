"""
Integration skill: Elasticsearch/OpenSearch search patterns.
Covers index mapping, queries, syncing from PostgreSQL, and performance optimization.
"""

ELASTICSEARCH_INDEX_MAPPING = {
    "products": {
        "description": "E-commerce product search with full-text, filters, and sorting",
        "python_elasticsearch": '''
from elasticsearch import AsyncElasticsearch

es = AsyncElasticsearch(hosts=[os.getenv('ELASTICSEARCH_URL')])

# Create index with mappings and settings
await es.indices.create(
    index="products",
    body={
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "analysis": {
                "analyzer": {
                    "english": {
                        "type": "english",
                        "stopwords": "_english_",
                    }
                }
            },
            "similarity": {
                "bm25": {
                    "type": "BM25",
                    "k1": 1.2,  # controls term frequency saturation
                    "b": 0.75,  # controls length normalization
                }
            },
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},  # UUID — exact match
                "name": {
                    "type": "text",
                    "analyzer": "english",
                    "search_analyzer": "english",
                    "fields": {
                        "keyword": {"type": "keyword"}  # For aggregations/sorting
                    }
                },
                "description": {
                    "type": "text",
                    "analyzer": "english",
                    "fields": {
                        "suggest": {
                            "type": "completion",  # Autocomplete
                            "analyzer": "simple"
                        }
                    }
                },
                "category": {"type": "keyword"},  # Exact match, aggregations
                "price": {"type": "float"},
                "in_stock": {"type": "boolean"},
                "tags": {"type": "keyword"},  # Filter by multiple values
                "created_at": {"type": "date"},
                "vendor": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "name": {"type": "text"}
                    }
                }
            }
        }
    }
)
''',
        "node_elasticsearch": '''
import { Client } from '@elastic/elasticsearch'

const client = new Client({ node: process.env.ELASTICSEARCH_URL })

await client.indices.create({
  index: 'products',
  body: {
    settings: { ... },
    mappings: { ... }
  }
})
''',
    },
    "users": {
        "description": "User search with partial matching, phonetic, and n-gram",
        "mapping": '''
{
  "properties": {
    "id": {"type": "keyword"},
    "email": {"type": "keyword"},
    "first_name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "phonetic": {
          "type": "text",
          "analyzer": "phonetic"
        },
        "ngram": {
          "type": "text",
          "analyzer": "ngram_analyzer"
        }
      }
    },
    "last_name": { ...same as first_name... },
    "bio": {"type": "text", "analyzer": "english"},
  }
}

# Custom analyzer for n-gram (partial matching):
# "analysis": {
#   "filter": {
#     "ngram_filter": {"type": "ngram", "min_gram": 2, "max_gram": 20}
#   },
#   "analyzer": {
#     "ngram_analyzer": {
#       "type": "custom",
#       "tokenizer": "standard",
#       "filter": ["lowercase", "ngram_filter"]
#     }
#   }
# }
''',
    },
}

ELASTICSEARCH_QUERY_PATTERNS = {
    "full_text_search": {
        "description": "Multimatch across multiple fields with boosting",
        "python": '''
response = await es.search(
    index="products",
    body={
        "query": {
            "multi_match": {
                "query": "wireless headphones",
                "fields": [
                    "name^3",           # Boost name field (3x)
                    "description^2",    # Boost description (2x)
                    "tags",
                    "vendor.name"
                ],
                "type": "best_fields",  # OR logic across fields
                "minimum_should_match": "75%",  # At least 75% of terms must match
            }
        },
        "highlight": {  # Highlight matching snippets
            "fields": {
                "description": {"fragment_size": 150, "number_of_fragments": 3}
            }
        }
    }
)
''',
    },
    "faceted_search": {
        "description": "Search with filters (category, price range) and aggregations",
        "python": '''
response = await es.search(
    index="products",
    body={
        "query": {
            "bool": {
                "must": [
                    {"match": {"name": "laptop"}}
                ],
                "filter": [
                    {"term": {"in_stock": True}},
                    {"range": {"price": {"gte": 500, "lte": 2000}}},
                    {"terms": {"category": ["electronics", "computers"]}},
                ]
            }
        },
        "aggs": {
            "categories": {
                "terms": {"field": "category", "size": 10}
            },
            "price_stats": {
                "stats": {"field": "price"}
            },
            "brands": {
                "terms": {"field": "vendor.name.keyword", "size": 20}
            }
        },
        "from": 0,
        "size": 20,
        "sort": [
            {"_score": {"order": "desc"}},     # By relevance first
            {"price": {"order": "asc"}},       # Then by price
        ]
    }
)

# Results:
# hits → matching documents
# aggregations → facet counts for UI filters
''',
    },
    "autocomplete": {
        "description": "Type-ahead search using completion suggester",
        "python": '''
response = await es.search(
    index="products",
    body={
        "suggest": {
            "product-suggest": {
                "prefix": "wire",
                "completion": {
                    "field": "description.suggest",
                    "fuzzy": {"fuzziness": "auto"},
                    "size": 5,
                }
            }
        }
    }
)

suggestions = response['suggest']['product-suggest'][0]['options']
# Returns: [{"text": "wireless charger", "_score": 1.0}, ...]
''',
    },
    "geo_search": {
        "description": "Find items near a location (stores, users)",
        "mapping": '''
"location": {
  "type": "geo_point"
}
''',
        "query": '''
{
  "query": {
    "bool": {
      "must": {"match": {"name": "coffee"}},
      "filter": {
        "geo_distance": {
          "distance": "10km",
          "location": {"lat": 40.7128, "lon": -74.0060}
        }
      }
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {"lat": 40.7128, "lon": -74.0060},
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
''',
    },
    "pagination": {
        "description": "Deep pagination vs search_after for large result sets",
        "avoid_deep_pagination": '''
# ❌ from: 10000, size: 20 (slow — ES must traverse 10k hits)
''',
        "use_search_after": '''
# 1. First page with sort + track_total_hits
response = await es.search(
    index="products",
    body={
        "query": {"match": {"category": "electronics"}},
        "sort": [{"price": "asc"}, "_id"],  # Deterministic sort (tie-breaker)
        "size": 20,
        "track_total_hits": False  # Don't count total for large datasets
    }
)

# 2. Next page with last sort values
last_sort = response['hits']['hits'][-1]['sort']
response = await es.search(
    index="products",
    body={
        "query": {...},
        "sort": [{"price": "asc"}, "_id"],
        "size": 20,
        "search_after": last_sort  # Use last sort values
    }
)
''',
    },
}

SYNCHRONIZATION_PATTERNS = '''
# Keep PostgreSQL (canonical source) in sync with Elasticsearch

# Method 1: Application-level sync (simplest)
# On every write to PostgreSQL, also write to ES
async def update_product(product_id: str, updates: dict):
    # 1. Update PostgreSQL
    product = await db.products.update(product_id, updates)

    # 2. Update Elasticsearch (async, fire-and-forget)
    await es.index(
        index="products",
        id=product_id,
        body=product.to_dict()
    )

    return product

# Method 2: Event-driven sync (more decoupled)
# Write to PostgreSQL → publish event to queue → consumer syncs to ES
{
    "event_type": "product.updated",
    "entity": "product",
    "entity_id": "abc123",
    "updated_fields": ["price", "stock"],
    "timestamp": "2024-01-01T00:00:00Z"
}

# Consumer:
async def handle_product_updated(event):
    product = await db.products.get(event.entity_id)
    if product:
        await es.index(index="products", id=product.id, body=product.to_dict())

# Method 3: Logstash (no code, configured externally)
# PostgreSQL → CDC (Debezium) or trigger → Logstash JDBC input → Elasticsearch output

# Indexing strategy:
# - Full reindex: Create new index (products_v2), swap alias atomically
# - Zero downtime: index to "products_v2", then POST /_aliases to switch
'''

INDEX_PERFORMANCE_TUNING = {
    "sharding": {
        "rule": "1 shard per 50GB max, 20-40GB ideal",
        "calculation": "Dataset size ÷ shard size = number of primary shards",
        "example": "200GB dataset → 5-10 primary shards (with 1 replica = 10-20 total shards)",
        "warning": "Too many shards: cluster overhead ↑. Too few: scaling limited.",
    },
    "replicas": {
        "production": "At least 1 replica for HA (primary + 1 copy)",
        "read_scaling": "Add more replicas (2-3) to handle read traffic",
        "cost": "Storage × (1 + replicas)",
    },
    "refresh_interval": {
        "default": "1 second — search near real-time",
        "bulk_load": "Set to 30s or -1 (disable) during large reindex, then back to 1s",
        "reindex_tradeoff": "Longer refresh → faster bulk load, but stale search results",
    },
    "translog": {
        "durability": "sync: async (default) or request (fsync after each request)",
        "performance": "async = faster but potential data loss on crash before fsync",
        "production": "request for critical data (e.g., transactions)",
    },
}

QUERY_PERFORMANCE_TRICKS = [
    "Use filter context for yes/no conditions (cached, no _score calculation)",
    "Avoid wildcard queries: 'pres*' OK, '*shion' BAD (leads to scanning)",
    "Use keyword fields for aggregations/sorting (not text fields)",
    "Limit size: default 10, max 1000 (use pagination for >1000)",
    "Select only needed fields: `_source: ['id', 'name']`",
    "Profile slow queries: `profile: true` in query body",
    "Use runtime fields instead of stored fields for derived values",
    "Cache frequent queries: define `request_cache: true` on query level",
    "Use search templates for repeated query patterns (pre-compiled)",
    "Monitor slowlog: set `index.search.slowlog.threshold.query.warn` (100ms)",
]

MAPPING_BEST_PRACTICES = [
    "Plan mappings upfront — changing field types requires reindex",
    "Use `keyword` for exact match, aggregations, sorting",
    "Use `text` for full-text search with analyzers",
    "Disable norms for fields not used in scoring (`norms: false`)",
    "Use `copy_to` to combine fields into a single search field",
    "Set `index: false` for fields you never search on (only storage)",
    "Use `null_value` for fields that may be null (avoid missing)",
    "Avoid dynamic mappings in production — define explicit mappings",
    "Use strict dynamic: `dynamic: strict` to reject unknown fields",
    "Version mappings: keep old index versions for rollback",
]

ELASTICSEARCH_CLUSTER_OPERATIONS = {
    "health_check": '''
GET /_cluster/health
# Response: {"status": "green|yellow|red", "number_of_nodes": 3, ...}
# green = all shards allocated
# yellow = primary shards allocated, replicas not (1 node cluster = yellow)
# red = some primary shards not allocated (cluster broken)
''',
    "index_stats": '''
GET /products/_stats
# Documents count, size on disk, deletions, etc.
''',
    "forcemerge": '''
# Reduce segment count (after bulk indexing)
POST /products/_forcemerge?max_num_segments=1
# Don't run frequently (expensive), run during low-traffic periods
''',
    "flush": '''
# Write translog to disk, clear cache
POST /products/_flush
''',
    "shard_allocation": '''
GET /_cat/shards?v  # View shard distribution
GET /_cat/allocation?v  # View disk usage per node
''',
    "reindex": '''
POST /_reindex
{
  "source": {"index": "products_old"},
  "dest": {"index": "products_new"}
}
# Requires both indices to exist, runs async
''',
    "rollover": '''
# Create new index when current index exceeds size/age
POST /products/_rollover
{
  "conditions": {
    "max_size": "50gb",
    "max_age": "30d"
  },
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1
  }
}
# Works with index alias → alias points to latest index
''',
}

ELASTICSEARCH_SECURITY = {
    "xpack": {
        "enabled": "X-Pack security features (commercial)",
        "features": [
            "TLS encryption in transit",
            "RBAC (role-based access control)",
            "Field-level security (hide sensitive fields)",
            "Document-level security (filter by user ID)",
            "Audit logging",
        ],
    },
    "opensource": {
        "alternatives": [
            "Search Guard (open source security plugin)",
            "Open Distro (AWS OpenSearch fork with security)",
        ],
    },
    "basic_auth": [
        "Create users: POST /_security/user/username",
        "Assign roles: POST /_security/role/rolename",
        "Enable TLS: configure keystore/truststore in elasticsearch.yml",
    ],
}

TESTING_ELASTICSEARCH = {
    "testcontainers": '''
# Use testcontainers to spin up ES in CI
from testcontainers.elasticsearch import ElasticSearchContainer

with ElasticSearchContainer() as container:
    es = Elasticsearch(hosts=[container.get_url()])
    # Perform tests against real ES instance
''',
    "mocking": [
        "Use elasticmock (limited, doesn't test queries)",
        "Better: integration test against real ES (testcontainers)",
    ],
    "fixtures": [
        "Create index with mappings before tests",
        "Index sample documents",
        "Delete index after tests (or use temporary index)",
    ],
}
