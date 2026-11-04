/* 由 contracts/ 的 examples 生成（scripts/gen_proto_mock.py）。请勿手改。纯 JSON，供脚本读回。 */
window.MOCK = {
 "examples": {
  "app.ping": {
   "ok": {
    "params": {},
    "result": {
     "ok": true,
     "uptimeMs": 183420
    }
   }
  },
  "app.bootstrap": {
   "ready": {
    "params": {},
    "result": {
     "protocolVersion": "1.0",
     "appVersion": "0.1.0",
     "dbSchemaVersion": 1,
     "platform": "macos",
     "engine": {
      "requested": "auto",
      "active": "jev_direct",
      "modelId": "jev-1.14.0",
      "jevdbAvailable": false
     },
     "markets": [
      "us"
     ],
     "configured": {
      "jevKey": true,
      "secEmail": true
     },
     "demoDataLoaded": true,
     "offline": false,
     "now": "2026-11-02T00:35:00Z"
    }
   },
   "unconfigured": {
    "params": {},
    "result": {
     "protocolVersion": "1.0",
     "appVersion": "0.1.0",
     "dbSchemaVersion": 1,
     "platform": "macos",
     "engine": {
      "requested": "auto",
      "active": "jev_direct",
      "modelId": "jev-1.14.0",
      "jevdbAvailable": false
     },
     "markets": [
      "us"
     ],
     "configured": {
      "jevKey": false,
      "secEmail": false
     },
     "demoDataLoaded": false,
     "offline": false,
     "now": "2026-11-02T00:35:00Z"
    }
   },
   "engine_fallback": {
    "params": {},
    "result": {
     "protocolVersion": "1.0",
     "appVersion": "0.1.0",
     "dbSchemaVersion": 1,
     "platform": "macos",
     "engine": {
      "requested": "jevdb",
      "active": "jev_direct",
      "modelId": "jev-1.14.0",
      "jevdbAvailable": false
     },
     "markets": [
      "us"
     ],
     "configured": {
      "jevKey": true,
      "secEmail": true
     },
     "demoDataLoaded": true,
     "offline": false,
     "now": "2026-11-02T00:35:00Z"
    }
   },
   "offline": {
    "params": {},
    "result": {
     "protocolVersion": "1.0",
     "appVersion": "0.1.0",
     "dbSchemaVersion": 1,
     "platform": "macos",
     "engine": {
      "requested": "auto",
      "active": "jev_direct",
      "modelId": "jev-1.14.0",
      "jevdbAvailable": false
     },
     "markets": [
      "us"
     ],
     "configured": {
      "jevKey": true,
      "secEmail": true
     },
     "demoDataLoaded": true,
     "offline": true,
     "now": "2026-11-02T00:35:00Z"
    }
   },
   "windows": {
    "params": {},
    "result": {
     "protocolVersion": "1.0",
     "appVersion": "0.1.0",
     "dbSchemaVersion": 1,
     "platform": "windows",
     "engine": {
      "requested": "auto",
      "active": "jev_direct",
      "modelId": "jev-1.14.0",
      "jevdbAvailable": false
     },
     "markets": [
      "us"
     ],
     "configured": {
      "jevKey": true,
      "secEmail": true
     },
     "demoDataLoaded": true,
     "offline": false,
     "now": "2026-11-02T00:35:00Z"
    }
   }
  },
  "app.shutdown": {
   "ok": {
    "params": {},
    "result": {
     "ok": true
    }
   }
  },
  "settings.get": {
   "configured": {
    "params": {},
    "result": {
     "engine": "auto",
     "modelId": "jev-1.14.0",
     "secContactEmail": "name@example.com",
     "dailyTokenBudget": 2000000,
     "firstScanLookbackDays": 7,
     "demoDataLoaded": true,
     "language": "zh-CN",
     "allowedDomains": [
      {
       "domain": "api.typesafe.ai",
       "purpose": "Jev 判定",
       "sends": "逻辑正文、失效条件、披露段落；不含持仓数量、成本、备注"
      },
      {
       "domain": "www.sec.gov",
       "purpose": "披露与标的表",
       "sends": "请求 URL 与含联系邮箱的 User-Agent"
      },
      {
       "domain": "data.sec.gov",
       "purpose": "披露与标的表",
       "sends": "请求 URL 与含联系邮箱的 User-Agent"
      },
      {
       "domain": "web.ifzq.gtimg.cn",
       "purpose": "日线行情（主源，覆盖美股/港股/A 股）",
       "sends": "股票代码与市场前缀"
      },
      {
       "domain": "api.nasdaq.com",
       "purpose": "日线行情（美股备源）",
       "sends": "股票代码"
      }
     ]
    }
   },
   "unconfigured": {
    "params": {},
    "result": {
     "engine": "auto",
     "modelId": "jev-1.14.0",
     "secContactEmail": null,
     "dailyTokenBudget": 2000000,
     "firstScanLookbackDays": 7,
     "demoDataLoaded": false,
     "language": "zh-CN",
     "allowedDomains": [
      {
       "domain": "api.typesafe.ai",
       "purpose": "Jev 判定",
       "sends": "逻辑正文、失效条件、披露段落；不含持仓数量、成本、备注"
      },
      {
       "domain": "www.sec.gov",
       "purpose": "披露与标的表",
       "sends": "请求 URL 与含联系邮箱的 User-Agent"
      },
      {
       "domain": "data.sec.gov",
       "purpose": "披露与标的表",
       "sends": "请求 URL 与含联系邮箱的 User-Agent"
      },
      {
       "domain": "web.ifzq.gtimg.cn",
       "purpose": "日线行情（主源，覆盖美股/港股/A 股）",
       "sends": "股票代码与市场前缀"
      },
      {
       "domain": "api.nasdaq.com",
       "purpose": "日线行情（美股备源）",
       "sends": "股票代码"
      }
     ]
    }
   }
  },
  "settings.update": {
   "ok": {
    "params": {
     "secContactEmail": "name@example.com",
     "dailyTokenBudget": 2000000
    },
    "result": {
     "engine": "auto",
     "modelId": "jev-1.14.0",
     "secContactEmail": "name@example.com",
     "dailyTokenBudget": 2000000,
     "firstScanLookbackDays": 7,
     "demoDataLoaded": true,
     "language": "zh-CN",
     "allowedDomains": [
      {
       "domain": "api.typesafe.ai",
       "purpose": "Jev 判定",
       "sends": "逻辑正文、失效条件、披露段落；不含持仓数量、成本、备注"
      },
      {
       "domain": "www.sec.gov",
       "purpose": "披露与标的表",
       "sends": "请求 URL 与含联系邮箱的 User-Agent"
      },
      {
       "domain": "data.sec.gov",
       "purpose": "披露与标的表",
       "sends": "请求 URL 与含联系邮箱的 User-Agent"
      },
      {
       "domain": "web.ifzq.gtimg.cn",
       "purpose": "日线行情（主源，覆盖美股/港股/A 股）",
       "sends": "股票代码与市场前缀"
      },
      {
       "domain": "api.nasdaq.com",
       "purpose": "日线行情（美股备源）",
       "sends": "股票代码"
      }
     ]
    }
   },
   "invalid_email": {
    "params": {
     "secContactEmail": "not-an-email"
    },
    "error": {
     "code": "INVALID_ARGUMENT",
     "message": "联系邮箱格式不正确",
     "data": {
      "retryable": false,
      "field": "secContactEmail"
     }
    }
   }
  },
  "settings.testConnection": {
   "ok": {
    "params": {},
    "result": {
     "ok": true,
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "checks": [
      {
       "name": "Jev",
       "ok": true,
       "latencyMs": 412,
       "message": "模型 jev-1.14.0 可用"
      },
      {
       "name": "SEC",
       "ok": true,
       "latencyMs": 236,
       "message": "data.sec.gov 可访问"
      },
      {
       "name": "JEVDB",
       "ok": false,
       "latencyMs": null,
       "message": "未找到 JEVDB 扩展，已使用 Jev 直连（同一模型）"
      }
     ]
    }
   },
   "failed": {
    "params": {},
    "result": {
     "ok": false,
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "checks": [
      {
       "name": "Jev",
       "ok": false,
       "latencyMs": null,
       "message": "密钥无效（401）。请重新填写 Jev 密钥。"
      },
      {
       "name": "SEC",
       "ok": true,
       "latencyMs": 251,
       "message": "data.sec.gov 可访问"
      },
      {
       "name": "JEVDB",
       "ok": false,
       "latencyMs": null,
       "message": "未找到 JEVDB 扩展，已使用 Jev 直连（同一模型）"
      }
     ]
    }
   }
  },
  "secrets.set": {
   "ok": {
    "params": {
     "name": "jevKey",
     "value": "<secret>"
    },
    "result": {
     "ok": true
    }
   }
  },
  "secrets.clear": {
   "ok": {
    "params": {
     "name": "jevKey"
    },
    "result": {
     "ok": true
    }
   }
  },
  "secrets.status": {
   "configured": {
    "params": {},
    "result": {
     "jevKey": true
    }
   },
   "none": {
    "params": {},
    "result": {
     "jevKey": false
    }
   }
  },
  "instruments.search": {
   "ze": {
    "params": {
     "query": "ze",
     "limit": 20
    },
    "result": {
     "items": [
      {
       "instrumentId": "us:ZZAR",
       "market": "us",
       "symbol": "ZZAR",
       "name": "Zenith Arc Robotics Inc.",
       "nameZh": "天顶弧机器人",
       "exchange": "NASDAQ",
       "currency": "USD",
       "isActive": true
      },
      {
       "instrumentId": "us:ZZEN",
       "market": "us",
       "symbol": "ZZEN",
       "name": "Zeta Energy Partners",
       "nameZh": "泽塔能源",
       "exchange": "NYSE",
       "currency": "USD",
       "isActive": true
      },
      {
       "instrumentId": "us:ZZMD",
       "market": "us",
       "symbol": "ZZMD",
       "name": "Zenmed Diagnostics Inc.",
       "nameZh": "泽美诊断",
       "exchange": "NASDAQ",
       "currency": "USD",
       "isActive": true
      },
      {
       "instrumentId": "us:ZZNW",
       "market": "us",
       "symbol": "ZZNW",
       "name": "Zenwave Networks Corp.",
       "nameZh": "泽波网络",
       "exchange": "NASDAQ",
       "currency": "USD",
       "isActive": true
      }
     ]
    }
   },
   "empty": {
    "params": {
     "query": "qqqq",
     "limit": 20
    },
    "result": {
     "items": []
    }
   },
   "cancelled": {
    "params": {
     "query": "zenith"
    },
    "error": {
     "code": "CANCELLED",
     "message": "已取消",
     "data": {
      "retryable": false
     }
    }
   }
  },
  "holdings.list": {
   "default": {
    "params": {},
    "result": {
     "items": [
      {
       "holdingId": "01JC8Z5V3Q00000000000032BJ",
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "quantity": "120.0000",
       "avgCost": "48.2000",
       "note": "核心仓位",
       "lastClose": 52.38,
       "lastCloseDate": "2026-10-30",
       "dayChangePct": 0.012,
       "marketValue": "6285.6000",
       "thesisCount": 2,
       "pendingCount": 2,
       "uncertainCount": 0,
       "status": "attention"
      },
      {
       "holdingId": "01JC8Z5V3Q00000000000032KW",
       "instrument": {
        "instrumentId": "us:ZZFD",
        "market": "us",
        "symbol": "ZZFD",
        "name": "Zephyr Foods Corp.",
        "nameZh": "和风食品",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "quantity": "300.0000",
       "avgCost": "22.1000",
       "note": null,
       "lastClose": 23.4,
       "lastCloseDate": "2026-10-30",
       "dayChangePct": -0.004,
       "marketValue": "7020.0000",
       "thesisCount": 1,
       "pendingCount": 0,
       "uncertainCount": 1,
       "status": "guarded"
      },
      {
       "holdingId": "01JC8Z5V3Q00000000000031W4",
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "quantity": "150.0000",
       "avgCost": "31.7500",
       "note": null,
       "lastClose": 27.95,
       "lastCloseDate": "2026-10-30",
       "dayChangePct": -0.031,
       "marketValue": "4192.5000",
       "thesisCount": 1,
       "pendingCount": 1,
       "uncertainCount": 1,
       "status": "attention"
      },
      {
       "holdingId": "01JC8Z5V3Q00000000000032KB",
       "instrument": {
        "instrumentId": "us:ZZBK",
        "market": "us",
        "symbol": "ZZBK",
        "name": "Zinc Bay Bancorp",
        "nameZh": "锌湾银行",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "quantity": "200.0000",
       "avgCost": "17.9000",
       "note": null,
       "lastClose": 18.62,
       "lastCloseDate": "2026-10-30",
       "dayChangePct": 0.006,
       "marketValue": "3724.0000",
       "thesisCount": 1,
       "pendingCount": 0,
       "uncertainCount": 0,
       "status": "guarded"
      },
      {
       "holdingId": "01JC8Z5V3Q00000000000032C6",
       "instrument": {
        "instrumentId": "us:ZZEN",
        "market": "us",
        "symbol": "ZZEN",
        "name": "Zeta Energy Partners",
        "nameZh": "泽塔能源",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "quantity": "100.0000",
       "avgCost": "38.5000",
       "note": null,
       "lastClose": 40.1,
       "lastCloseDate": "2026-10-30",
       "dayChangePct": 0.009,
       "marketValue": "4010.0000",
       "thesisCount": 0,
       "pendingCount": 0,
       "uncertainCount": 0,
       "status": "unguarded"
      },
      {
       "holdingId": "01JC8Z5V3Q00000000000032DC",
       "instrument": {
        "instrumentId": "us:ZZMD",
        "market": "us",
        "symbol": "ZZMD",
        "name": "Zenmed Diagnostics Inc.",
        "nameZh": "泽美诊断",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "quantity": "0.0000",
       "avgCost": null,
       "note": "只关注",
       "lastClose": 64.2,
       "lastCloseDate": "2026-10-30",
       "dayChangePct": -0.002,
       "marketValue": "0.0000",
       "thesisCount": 0,
       "pendingCount": 0,
       "uncertainCount": 0,
       "status": "unguarded"
      }
     ],
     "asOf": "2026-11-02T00:35:00Z"
    }
   },
   "empty": {
    "params": {},
    "result": {
     "items": [],
     "asOf": "2026-11-02T00:35:00Z"
    }
   }
  },
  "holdings.upsert": {
   "ok": {
    "params": {
     "instrumentId": "us:ZZAR",
     "quantity": "120",
     "avgCost": "48.20",
     "note": "核心仓位"
    },
    "result": {
     "holdingId": "01JC8Z5V3Q00000000000032BJ",
     "instrument": {
      "instrumentId": "us:ZZAR",
      "market": "us",
      "symbol": "ZZAR",
      "name": "Zenith Arc Robotics Inc.",
      "nameZh": "天顶弧机器人",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "quantity": "120.0000",
     "avgCost": "48.2000",
     "note": "核心仓位",
     "lastClose": 52.38,
     "lastCloseDate": "2026-10-30",
     "dayChangePct": 0.012,
     "marketValue": "6285.6000",
     "thesisCount": 2,
     "pendingCount": 2,
     "uncertainCount": 0,
     "status": "attention"
    }
   },
   "negative": {
    "params": {
     "instrumentId": "us:ZZAR",
     "quantity": "-5"
    },
    "error": {
     "code": "INVALID_ARGUMENT",
     "message": "数量不能为负数",
     "data": {
      "retryable": false,
      "field": "quantity"
     }
    }
   }
  },
  "holdings.archive": {
   "ok": {
    "params": {
     "instrumentId": "us:ZZMD"
    },
    "result": {
     "ok": true
    }
   }
  },
  "prices.refresh": {
   "ok": {
    "params": {
     "instrumentIds": [
      "us:ZZAR"
     ]
    },
    "result": {
     "updated": 1,
     "failed": [],
     "asOf": "2026-10-30"
    }
   },
   "offline": {
    "params": {},
    "error": {
     "code": "SOURCE_UNAVAILABLE",
     "message": "行情源暂时无法访问，已使用 10 月 30 日的收盘价。",
     "data": {
      "retryable": true
     }
    }
   }
  },
  "thesis.list": {
   "zzar": {
    "params": {
     "instrumentId": "us:ZZAR",
     "status": "active"
    },
    "result": {
     "items": [
      {
       "thesisId": "01JC8Z5V3Q00000000000063A1",
       "instrumentId": "us:ZZAR",
       "version": 2,
       "statement": "控股股东长期持股，不会大幅减持",
       "killCondition": "控股股东减持超过 2%",
       "status": "active",
       "createdAt": "2026-09-02T02:10:00Z",
       "updatedAt": "2026-10-12T11:03:00Z",
       "versionCount": 2,
       "lastDecision": {
        "decisionId": "01JC8Z5V3Q00000000000094Z1",
        "relation": "overturn",
        "headline": 0.93,
        "createdAt": "2026-11-02T00:31:12Z",
        "eventTitle": "8-K: Other Events — Completed sale by controlling stockholder"
       }
      },
      {
       "thesisId": "01JC8Z5V3Q00000000000063A2",
       "instrumentId": "us:ZZAR",
       "version": 1,
       "statement": "Management keeps R&D spending above 15% of revenue",
       "killCondition": null,
       "status": "active",
       "createdAt": "2026-09-02T02:15:00Z",
       "updatedAt": "2026-09-02T02:15:00Z",
       "versionCount": 1,
       "lastDecision": {
        "decisionId": "01JC8Z5V3Q00000000000094Z3",
        "relation": "weaken",
        "headline": 0.74,
        "createdAt": "2026-11-02T00:31:12Z",
        "eventTitle": "8-K: Results of Operations — Third Quarter 2026"
       }
      }
     ]
    }
   },
   "zzfd": {
    "params": {
     "instrumentId": "us:ZZFD",
     "status": "active"
    },
    "result": {
     "items": [
      {
       "thesisId": "01JC8Z5V3Q00000000000063A3",
       "instrumentId": "us:ZZFD",
       "version": 1,
       "statement": "公司持续回购股票并维持分红",
       "killCondition": "暂停回购或削减分红",
       "status": "active",
       "createdAt": "2026-09-03T08:20:00Z",
       "updatedAt": "2026-09-03T08:20:00Z",
       "versionCount": 1,
       "lastDecision": {
        "decisionId": "01JC8Z5V3Q00000000000094Z4",
        "relation": "uncertain",
        "headline": 0.55,
        "createdAt": "2026-11-02T00:31:12Z",
        "eventTitle": "8-K: Quarterly dividend and share repurchase update"
       }
      }
     ]
    }
   },
   "zzcl": {
    "params": {
     "instrumentId": "us:ZZCL",
     "status": "active"
    },
    "result": {
     "items": [
      {
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "instrumentId": "us:ZZCL",
       "version": 2,
       "statement": "云业务收入保持两位数增长，同比不低于 10%",
       "killCondition": "云业务收入同比增速低于 10%",
       "status": "active",
       "createdAt": "2026-09-05T01:40:00Z",
       "updatedAt": "2026-10-20T03:00:00Z",
       "versionCount": 2,
       "lastDecision": {
        "decisionId": "01JC8Z5V3Q00000000000094Z2",
        "relation": "overturn",
        "headline": 0.92,
        "createdAt": "2026-11-02T00:31:12Z",
        "eventTitle": "6-K: Zhongzhi Cloud Reports Third Quarter 2026 Results"
       }
      }
     ]
    }
   },
   "zzbk": {
    "params": {
     "instrumentId": "us:ZZBK",
     "status": "active"
    },
    "result": {
     "items": [
      {
       "thesisId": "01JC8Z5V3Q00000000000063A5",
       "instrumentId": "us:ZZBK",
       "version": 1,
       "statement": "存款成本保持稳定，净息差不收窄",
       "killCondition": null,
       "status": "active",
       "createdAt": "2026-09-08T03:00:00Z",
       "updatedAt": "2026-09-08T03:00:00Z",
       "versionCount": 1,
       "lastDecision": {
        "decisionId": "01JC8Z5V3Q00000000000094Z6",
        "relation": "weaken",
        "headline": 0.72,
        "createdAt": "2026-10-28T00:20:00Z",
        "eventTitle": "8-K: Third quarter 2026 net interest margin"
       }
      }
     ]
    }
   },
   "empty": {
    "params": {
     "instrumentId": "us:ZZMD",
     "status": "active"
    },
    "result": {
     "items": []
    }
   }
  },
  "thesis.create": {
   "ok": {
    "params": {
     "instrumentId": "us:ZZEN",
     "statement": "油价高位时公司现金流保持充裕",
     "killCondition": "资本开支超过经营现金流"
    },
    "result": {
     "thesisId": "01JC8Z5V3Q00000000000063A6",
     "instrumentId": "us:ZZEN",
     "version": 1,
     "statement": "油价高位时公司现金流保持充裕",
     "killCondition": "资本开支超过经营现金流",
     "status": "active",
     "createdAt": "2026-11-02T00:35:00Z",
     "updatedAt": "2026-11-02T00:35:00Z",
     "versionCount": 1,
     "lastDecision": null
    }
   },
   "empty": {
    "params": {
     "instrumentId": "us:ZZEN",
     "statement": "   "
    },
    "error": {
     "code": "INVALID_ARGUMENT",
     "message": "逻辑内容不能为空",
     "data": {
      "retryable": false,
      "field": "statement"
     }
    }
   },
   "too_long": {
    "params": {
     "instrumentId": "us:ZZEN",
     "statement": "字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字"
    },
    "error": {
     "code": "INVALID_ARGUMENT",
     "message": "逻辑最多 500 字，当前 501 字",
     "data": {
      "retryable": false,
      "field": "statement",
      "length": 501,
      "max": 500
     }
    }
   },
   "limit_reached": {
    "params": {
     "instrumentId": "us:ZZAR",
     "statement": "第六条逻辑"
    },
    "error": {
     "code": "INVALID_ARGUMENT",
     "message": "每只股票最多 5 条有效逻辑",
     "data": {
      "retryable": false,
      "field": "instrumentId",
      "max": 5
     }
    }
   }
  },
  "thesis.update": {
   "ok": {
    "params": {
     "thesisId": "01JC8Z5V3Q00000000000063A1",
     "statement": "控股股东长期持股，不会大幅减持或质押股份",
     "killCondition": "控股股东减持超过 2%",
     "expectedVersion": 2
    },
    "result": {
     "thesisId": "01JC8Z5V3Q00000000000063A1",
     "instrumentId": "us:ZZAR",
     "version": 3,
     "statement": "控股股东长期持股，不会大幅减持或质押股份",
     "killCondition": "控股股东减持超过 2%",
     "status": "active",
     "createdAt": "2026-09-02T02:10:00Z",
     "updatedAt": "2026-11-02T00:35:00Z",
     "versionCount": 3,
     "lastDecision": {
      "decisionId": "01JC8Z5V3Q00000000000094Z1",
      "relation": "overturn",
      "headline": 0.93,
      "createdAt": "2026-11-02T00:31:12Z",
      "eventTitle": "8-K: Other Events — Completed sale by controlling stockholder"
     }
    }
   },
   "conflict": {
    "params": {
     "thesisId": "01JC8Z5V3Q00000000000063A1",
     "statement": "x",
     "expectedVersion": 1
    },
    "error": {
     "code": "CONFLICT",
     "message": "这条逻辑已被修改，请刷新后再试",
     "data": {
      "retryable": false,
      "currentVersion": 2
     }
    }
   }
  },
  "thesis.archive": {
   "ok": {
    "params": {
     "thesisId": "01JC8Z5V3Q00000000000063A2"
    },
    "result": {
     "ok": true
    }
   }
  },
  "thesis.versions": {
   "default": {
    "params": {
     "thesisId": "01JC8Z5V3Q00000000000063A1"
    },
    "result": {
     "items": [
      {
       "version": 2,
       "statement": "控股股东长期持股，不会大幅减持",
       "killCondition": "控股股东减持超过 2%",
       "createdAt": "2026-10-12T11:03:00Z"
      },
      {
       "version": 1,
       "statement": "控股股东长期持股",
       "killCondition": null,
       "createdAt": "2026-09-02T02:10:00Z"
      }
     ]
    }
   }
  },
  "inbox.list": {
   "pending": {
    "params": {},
    "result": {
     "asOf": "2026-11-02T00:35:00Z",
     "summary": {
      "pendingCount": 3,
      "overturnCount": 2,
      "weakenCount": 1,
      "uncertainCount": 2,
      "processedCount": 1
     },
     "items": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z1",
       "thesisId": "01JC8Z5V3Q00000000000063A1",
       "thesisVersion": 2,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "控股股东长期持股，不会大幅减持",
       "killCondition": "控股股东减持超过 2%",
       "relation": "overturn",
       "headline": 0.93,
       "probabilities": {
        "relevant": 0.97,
        "against": 0.89,
        "contradicts": 0.84,
        "killMet": 0.93,
        "supports": 0.03
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000001",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Other Events — Completed sale by controlling stockholder",
        "formType": "8-K",
        "publishedAt": "2026-10-30T20:12:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000001/zzar-8k.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering.",
        "passageText": "Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering. Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
        "sentenceStart": 24,
        "sentenceEnd": 265,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z2",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "overturn",
       "headline": 0.92,
       "probabilities": {
        "relevant": 0.98,
        "against": 0.92,
        "contradicts": 0.81,
        "killMet": 0.88,
        "supports": 0.02
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000002",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Zhongzhi Cloud Reports Third Quarter 2026 Results",
        "formType": "6-K",
        "publishedAt": "2026-10-30T11:30:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000002/zzcl-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter.",
        "passageText": "Zhongzhi Cloud Ltd. today announced unaudited financial results for the third quarter ended September 30, 2026. Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter. Total revenue was RMB 2,031 million, an increase of 11.3% year-over-year. The Company expects cloud services revenue growth to remain in the single digits for the fourth quarter as it completes the migration of legacy customers.",
        "sentenceStart": 112,
        "sentenceEnd": 251,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z3",
       "thesisId": "01JC8Z5V3Q00000000000063A2",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "Management keeps R&D spending above 15% of revenue",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.74,
       "probabilities": {
        "relevant": 0.95,
        "against": 0.74,
        "contradicts": 0.41,
        "killMet": null,
        "supports": 0.06
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000003",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Results of Operations — Third Quarter 2026",
        "formType": "8-K",
        "publishedAt": "2026-10-29T20:05:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000003/zzar-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter.",
        "passageText": "Zenith Arc Robotics reported third quarter revenue of $214.6 million, up 9% from a year earlier. Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter. The Company said it is prioritizing near-term profitability and has paused two early-stage programs.",
        "sentenceStart": 97,
        "sentenceEnd": 248,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      }
     ],
     "uncertain": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z4",
       "thesisId": "01JC8Z5V3Q00000000000063A3",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZFD",
        "market": "us",
        "symbol": "ZZFD",
        "name": "Zephyr Foods Corp.",
        "nameZh": "和风食品",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "公司持续回购股票并维持分红",
       "killCondition": "暂停回购或削减分红",
       "relation": "uncertain",
       "headline": 0.55,
       "probabilities": {
        "relevant": 0.93,
        "against": 0.55,
        "contradicts": 0.22,
        "killMet": 0.31,
        "supports": 0.18
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000004",
        "instrumentId": "us:ZZFD",
        "title": "8-K: Quarterly dividend and share repurchase update",
        "formType": "8-K",
        "publishedAt": "2026-10-29T13:02:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000004/zzfd-8k.htm"
       },
       "evidence": {
        "kind": "passage",
        "text": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
        "passageText": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
        "sentenceStart": null,
        "sentenceEnd": null,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z5",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "uncertain",
       "headline": 0.42,
       "probabilities": {
        "relevant": 0.58,
        "against": 0.42,
        "contradicts": 0.2,
        "killMet": 0.35,
        "supports": 0.1
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000006",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Notice of Extraordinary General Meeting",
        "formType": "6-K",
        "publishedAt": "2026-10-28T09:45:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000006/zzcl-6k.htm"
       },
       "evidence": {
        "kind": "title",
        "text": "6-K: Notice of Extraordinary General Meeting",
        "passageText": "6-K: Notice of Extraordinary General Meeting",
        "sentenceStart": null,
        "sentenceEnd": null,
        "filePart": "标题"
       },
       "contentStatus": "title_only",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      }
     ],
     "processed": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z6",
       "thesisId": "01JC8Z5V3Q00000000000063A5",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZBK",
        "market": "us",
        "symbol": "ZZBK",
        "name": "Zinc Bay Bancorp",
        "nameZh": "锌湾银行",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "存款成本保持稳定，净息差不收窄",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.72,
       "probabilities": {
        "relevant": 0.96,
        "against": 0.72,
        "contradicts": 0.3,
        "killMet": null,
        "supports": 0.08
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000005",
        "instrumentId": "us:ZZBK",
        "title": "8-K: Third quarter 2026 net interest margin",
        "formType": "8-K",
        "publishedAt": "2026-10-27T21:15:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000005/zzbk-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter.",
        "passageText": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
        "sentenceStart": 0,
        "sentenceEnd": 131,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-10-28T00:20:00Z",
       "action": {
        "action": "still_valid",
        "note": "只收窄了 3 个基点，管理层预计稳定",
        "actedAt": "2026-10-28T02:40:00Z"
       }
      }
     ],
     "lastScan": {
      "runId": "01JC8Z5V3Q000000000000C6M1",
      "status": "succeeded",
      "finishedAt": "2026-11-02T00:31:12Z",
      "stats": {
       "instruments": 4,
       "skippedNoThesis": 2,
       "filings": 6,
       "passages": 17,
       "decisions": 21
      },
      "error": null
     },
     "dataStatus": {
      "market": "us",
      "marketState": "closed",
      "nextOpenAt": "2026-11-02T14:30:00Z",
      "source": {
       "name": "SEC EDGAR",
       "state": "ok",
       "lastSuccessAt": "2026-11-02T00:31:12Z",
       "message": null
      },
      "engine": {
       "active": "jev_direct",
       "modelId": "jev-1.14.0",
       "state": "ok"
      },
      "budget": {
       "usedTokens": 18420,
       "limitTokens": 2000000,
       "resetAt": "2026-11-03T00:00:00Z"
      },
      "offline": false
     },
     "setup": {
      "holdings": 6,
      "activeTheses": 5,
      "scannableInstruments": 4
     }
    }
   },
   "empty": {
    "params": {},
    "result": {
     "asOf": "2026-11-02T00:35:00Z",
     "summary": {
      "pendingCount": 0,
      "overturnCount": 0,
      "weakenCount": 0,
      "uncertainCount": 0,
      "processedCount": 4
     },
     "items": [],
     "uncertain": [],
     "processed": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z1",
       "thesisId": "01JC8Z5V3Q00000000000063A1",
       "thesisVersion": 2,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "控股股东长期持股，不会大幅减持",
       "killCondition": "控股股东减持超过 2%",
       "relation": "overturn",
       "headline": 0.93,
       "probabilities": {
        "relevant": 0.97,
        "against": 0.89,
        "contradicts": 0.84,
        "killMet": 0.93,
        "supports": 0.03
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000001",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Other Events — Completed sale by controlling stockholder",
        "formType": "8-K",
        "publishedAt": "2026-10-30T20:12:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000001/zzar-8k.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering.",
        "passageText": "Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering. Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
        "sentenceStart": 24,
        "sentenceEnd": 265,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": {
        "action": "exit_intent",
        "note": "先观察一周",
        "actedAt": "2026-11-02T00:37:00Z"
       }
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z2",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "overturn",
       "headline": 0.92,
       "probabilities": {
        "relevant": 0.98,
        "against": 0.92,
        "contradicts": 0.81,
        "killMet": 0.88,
        "supports": 0.02
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000002",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Zhongzhi Cloud Reports Third Quarter 2026 Results",
        "formType": "6-K",
        "publishedAt": "2026-10-30T11:30:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000002/zzcl-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter.",
        "passageText": "Zhongzhi Cloud Ltd. today announced unaudited financial results for the third quarter ended September 30, 2026. Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter. Total revenue was RMB 2,031 million, an increase of 11.3% year-over-year. The Company expects cloud services revenue growth to remain in the single digits for the fourth quarter as it completes the migration of legacy customers.",
        "sentenceStart": 112,
        "sentenceEnd": 251,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": {
        "action": "revise",
        "note": null,
        "actedAt": "2026-11-02T00:37:00Z"
       }
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z3",
       "thesisId": "01JC8Z5V3Q00000000000063A2",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "Management keeps R&D spending above 15% of revenue",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.74,
       "probabilities": {
        "relevant": 0.95,
        "against": 0.74,
        "contradicts": 0.41,
        "killMet": null,
        "supports": 0.06
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000003",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Results of Operations — Third Quarter 2026",
        "formType": "8-K",
        "publishedAt": "2026-10-29T20:05:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000003/zzar-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter.",
        "passageText": "Zenith Arc Robotics reported third quarter revenue of $214.6 million, up 9% from a year earlier. Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter. The Company said it is prioritizing near-term profitability and has paused two early-stage programs.",
        "sentenceStart": 97,
        "sentenceEnd": 248,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": {
        "action": "ignore",
        "note": null,
        "actedAt": "2026-11-02T00:37:00Z"
       }
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z6",
       "thesisId": "01JC8Z5V3Q00000000000063A5",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZBK",
        "market": "us",
        "symbol": "ZZBK",
        "name": "Zinc Bay Bancorp",
        "nameZh": "锌湾银行",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "存款成本保持稳定，净息差不收窄",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.72,
       "probabilities": {
        "relevant": 0.96,
        "against": 0.72,
        "contradicts": 0.3,
        "killMet": null,
        "supports": 0.08
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000005",
        "instrumentId": "us:ZZBK",
        "title": "8-K: Third quarter 2026 net interest margin",
        "formType": "8-K",
        "publishedAt": "2026-10-27T21:15:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000005/zzbk-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter.",
        "passageText": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
        "sentenceStart": 0,
        "sentenceEnd": 131,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-10-28T00:20:00Z",
       "action": {
        "action": "still_valid",
        "note": "只收窄了 3 个基点，管理层预计稳定",
        "actedAt": "2026-10-28T02:40:00Z"
       }
      }
     ],
     "lastScan": {
      "runId": "01JC8Z5V3Q000000000000C6M1",
      "status": "succeeded",
      "finishedAt": "2026-11-02T00:31:12Z",
      "stats": {
       "instruments": 4,
       "skippedNoThesis": 2,
       "filings": 6,
       "passages": 17,
       "decisions": 21
      },
      "error": null
     },
     "dataStatus": {
      "market": "us",
      "marketState": "closed",
      "nextOpenAt": "2026-11-02T14:30:00Z",
      "source": {
       "name": "SEC EDGAR",
       "state": "ok",
       "lastSuccessAt": "2026-11-02T00:31:12Z",
       "message": null
      },
      "engine": {
       "active": "jev_direct",
       "modelId": "jev-1.14.0",
       "state": "ok"
      },
      "budget": {
       "usedTokens": 18420,
       "limitTokens": 2000000,
       "resetAt": "2026-11-03T00:00:00Z"
      },
      "offline": false
     },
     "setup": {
      "holdings": 6,
      "activeTheses": 5,
      "scannableInstruments": 4
     }
    }
   },
   "scan_failed": {
    "params": {},
    "result": {
     "asOf": "2026-11-02T00:35:00Z",
     "summary": {
      "pendingCount": 3,
      "overturnCount": 2,
      "weakenCount": 1,
      "uncertainCount": 2,
      "processedCount": 1
     },
     "items": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z1",
       "thesisId": "01JC8Z5V3Q00000000000063A1",
       "thesisVersion": 2,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "控股股东长期持股，不会大幅减持",
       "killCondition": "控股股东减持超过 2%",
       "relation": "overturn",
       "headline": 0.93,
       "probabilities": {
        "relevant": 0.97,
        "against": 0.89,
        "contradicts": 0.84,
        "killMet": 0.93,
        "supports": 0.03
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000001",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Other Events — Completed sale by controlling stockholder",
        "formType": "8-K",
        "publishedAt": "2026-10-30T20:12:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000001/zzar-8k.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering.",
        "passageText": "Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering. Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
        "sentenceStart": 24,
        "sentenceEnd": 265,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z2",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "overturn",
       "headline": 0.92,
       "probabilities": {
        "relevant": 0.98,
        "against": 0.92,
        "contradicts": 0.81,
        "killMet": 0.88,
        "supports": 0.02
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000002",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Zhongzhi Cloud Reports Third Quarter 2026 Results",
        "formType": "6-K",
        "publishedAt": "2026-10-30T11:30:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000002/zzcl-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter.",
        "passageText": "Zhongzhi Cloud Ltd. today announced unaudited financial results for the third quarter ended September 30, 2026. Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter. Total revenue was RMB 2,031 million, an increase of 11.3% year-over-year. The Company expects cloud services revenue growth to remain in the single digits for the fourth quarter as it completes the migration of legacy customers.",
        "sentenceStart": 112,
        "sentenceEnd": 251,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z3",
       "thesisId": "01JC8Z5V3Q00000000000063A2",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "Management keeps R&D spending above 15% of revenue",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.74,
       "probabilities": {
        "relevant": 0.95,
        "against": 0.74,
        "contradicts": 0.41,
        "killMet": null,
        "supports": 0.06
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000003",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Results of Operations — Third Quarter 2026",
        "formType": "8-K",
        "publishedAt": "2026-10-29T20:05:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000003/zzar-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter.",
        "passageText": "Zenith Arc Robotics reported third quarter revenue of $214.6 million, up 9% from a year earlier. Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter. The Company said it is prioritizing near-term profitability and has paused two early-stage programs.",
        "sentenceStart": 97,
        "sentenceEnd": 248,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      }
     ],
     "uncertain": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z4",
       "thesisId": "01JC8Z5V3Q00000000000063A3",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZFD",
        "market": "us",
        "symbol": "ZZFD",
        "name": "Zephyr Foods Corp.",
        "nameZh": "和风食品",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "公司持续回购股票并维持分红",
       "killCondition": "暂停回购或削减分红",
       "relation": "uncertain",
       "headline": 0.55,
       "probabilities": {
        "relevant": 0.93,
        "against": 0.55,
        "contradicts": 0.22,
        "killMet": 0.31,
        "supports": 0.18
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000004",
        "instrumentId": "us:ZZFD",
        "title": "8-K: Quarterly dividend and share repurchase update",
        "formType": "8-K",
        "publishedAt": "2026-10-29T13:02:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000004/zzfd-8k.htm"
       },
       "evidence": {
        "kind": "passage",
        "text": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
        "passageText": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
        "sentenceStart": null,
        "sentenceEnd": null,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z5",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "uncertain",
       "headline": 0.42,
       "probabilities": {
        "relevant": 0.58,
        "against": 0.42,
        "contradicts": 0.2,
        "killMet": 0.35,
        "supports": 0.1
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000006",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Notice of Extraordinary General Meeting",
        "formType": "6-K",
        "publishedAt": "2026-10-28T09:45:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000006/zzcl-6k.htm"
       },
       "evidence": {
        "kind": "title",
        "text": "6-K: Notice of Extraordinary General Meeting",
        "passageText": "6-K: Notice of Extraordinary General Meeting",
        "sentenceStart": null,
        "sentenceEnd": null,
        "filePart": "标题"
       },
       "contentStatus": "title_only",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      }
     ],
     "processed": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z6",
       "thesisId": "01JC8Z5V3Q00000000000063A5",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZBK",
        "market": "us",
        "symbol": "ZZBK",
        "name": "Zinc Bay Bancorp",
        "nameZh": "锌湾银行",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "存款成本保持稳定，净息差不收窄",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.72,
       "probabilities": {
        "relevant": 0.96,
        "against": 0.72,
        "contradicts": 0.3,
        "killMet": null,
        "supports": 0.08
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000005",
        "instrumentId": "us:ZZBK",
        "title": "8-K: Third quarter 2026 net interest margin",
        "formType": "8-K",
        "publishedAt": "2026-10-27T21:15:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000005/zzbk-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter.",
        "passageText": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
        "sentenceStart": 0,
        "sentenceEnd": 131,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-10-28T00:20:00Z",
       "action": {
        "action": "still_valid",
        "note": "只收窄了 3 个基点，管理层预计稳定",
        "actedAt": "2026-10-28T02:40:00Z"
       }
      }
     ],
     "lastScan": {
      "runId": "01JC8Z5V3Q000000000000C6M9",
      "status": "failed",
      "finishedAt": "2026-11-02T00:36:02Z",
      "stats": {
       "instruments": 0,
       "skippedNoThesis": 0,
       "filings": 0,
       "passages": 0,
       "decisions": 0
      },
      "error": {
       "code": "SOURCE_UNAVAILABLE",
       "message": "无法连接 SEC，请检查网络后重试。已显示 11 月 2 日 08:31 的结果。"
      }
     },
     "dataStatus": {
      "market": "us",
      "marketState": "closed",
      "nextOpenAt": "2026-11-02T14:30:00Z",
      "source": {
       "name": "SEC EDGAR",
       "state": "down",
       "lastSuccessAt": "2026-11-02T00:31:12Z",
       "message": "SEC 暂时无法访问，当前显示的是 11 月 2 日 08:31 的结果"
      },
      "engine": {
       "active": "jev_direct",
       "modelId": "jev-1.14.0",
       "state": "ok"
      },
      "budget": {
       "usedTokens": 18420,
       "limitTokens": 2000000,
       "resetAt": "2026-11-03T00:00:00Z"
      },
      "offline": false
     },
     "setup": {
      "holdings": 6,
      "activeTheses": 5,
      "scannableInstruments": 4
     }
    }
   },
   "no_holdings": {
    "params": {},
    "result": {
     "asOf": "2026-11-02T00:35:00Z",
     "summary": {
      "pendingCount": 0,
      "overturnCount": 0,
      "weakenCount": 0,
      "uncertainCount": 0,
      "processedCount": 0
     },
     "items": [],
     "uncertain": [],
     "processed": [],
     "lastScan": null,
     "dataStatus": {
      "market": "us",
      "marketState": "closed",
      "nextOpenAt": "2026-11-02T14:30:00Z",
      "source": {
       "name": "SEC EDGAR",
       "state": "ok",
       "lastSuccessAt": "2026-11-02T00:31:12Z",
       "message": null
      },
      "engine": {
       "active": "jev_direct",
       "modelId": "jev-1.14.0",
       "state": "ok"
      },
      "budget": {
       "usedTokens": 0,
       "limitTokens": 2000000,
       "resetAt": "2026-11-03T00:00:00Z"
      },
      "offline": false
     },
     "setup": {
      "holdings": 0,
      "activeTheses": 0,
      "scannableInstruments": 0
     }
    }
   },
   "never_scanned": {
    "params": {},
    "result": {
     "asOf": "2026-11-02T00:35:00Z",
     "summary": {
      "pendingCount": 0,
      "overturnCount": 0,
      "weakenCount": 0,
      "uncertainCount": 0,
      "processedCount": 0
     },
     "items": [],
     "uncertain": [],
     "processed": [],
     "lastScan": null,
     "dataStatus": {
      "market": "us",
      "marketState": "closed",
      "nextOpenAt": "2026-11-02T14:30:00Z",
      "source": {
       "name": "SEC EDGAR",
       "state": "ok",
       "lastSuccessAt": "2026-11-02T00:31:12Z",
       "message": null
      },
      "engine": {
       "active": "jev_direct",
       "modelId": "jev-1.14.0",
       "state": "ok"
      },
      "budget": {
       "usedTokens": 0,
       "limitTokens": 2000000,
       "resetAt": "2026-11-03T00:00:00Z"
      },
      "offline": false
     },
     "setup": {
      "holdings": 6,
      "activeTheses": 5,
      "scannableInstruments": 4
     }
    }
   },
   "offline": {
    "params": {},
    "result": {
     "asOf": "2026-11-02T00:35:00Z",
     "summary": {
      "pendingCount": 3,
      "overturnCount": 2,
      "weakenCount": 1,
      "uncertainCount": 2,
      "processedCount": 1
     },
     "items": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z1",
       "thesisId": "01JC8Z5V3Q00000000000063A1",
       "thesisVersion": 2,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "控股股东长期持股，不会大幅减持",
       "killCondition": "控股股东减持超过 2%",
       "relation": "overturn",
       "headline": 0.93,
       "probabilities": {
        "relevant": 0.97,
        "against": 0.89,
        "contradicts": 0.84,
        "killMet": 0.93,
        "supports": 0.03
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000001",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Other Events — Completed sale by controlling stockholder",
        "formType": "8-K",
        "publishedAt": "2026-10-30T20:12:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000001/zzar-8k.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering.",
        "passageText": "Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering. Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
        "sentenceStart": 24,
        "sentenceEnd": 265,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z2",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "overturn",
       "headline": 0.92,
       "probabilities": {
        "relevant": 0.98,
        "against": 0.92,
        "contradicts": 0.81,
        "killMet": 0.88,
        "supports": 0.02
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000002",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Zhongzhi Cloud Reports Third Quarter 2026 Results",
        "formType": "6-K",
        "publishedAt": "2026-10-30T11:30:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000002/zzcl-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter.",
        "passageText": "Zhongzhi Cloud Ltd. today announced unaudited financial results for the third quarter ended September 30, 2026. Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter. Total revenue was RMB 2,031 million, an increase of 11.3% year-over-year. The Company expects cloud services revenue growth to remain in the single digits for the fourth quarter as it completes the migration of legacy customers.",
        "sentenceStart": 112,
        "sentenceEnd": 251,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z3",
       "thesisId": "01JC8Z5V3Q00000000000063A2",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "Management keeps R&D spending above 15% of revenue",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.74,
       "probabilities": {
        "relevant": 0.95,
        "against": 0.74,
        "contradicts": 0.41,
        "killMet": null,
        "supports": 0.06
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000003",
        "instrumentId": "us:ZZAR",
        "title": "8-K: Results of Operations — Third Quarter 2026",
        "formType": "8-K",
        "publishedAt": "2026-10-29T20:05:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000003/zzar-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter.",
        "passageText": "Zenith Arc Robotics reported third quarter revenue of $214.6 million, up 9% from a year earlier. Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter. The Company said it is prioritizing near-term profitability and has paused two early-stage programs.",
        "sentenceStart": 97,
        "sentenceEnd": 248,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      }
     ],
     "uncertain": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z4",
       "thesisId": "01JC8Z5V3Q00000000000063A3",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZFD",
        "market": "us",
        "symbol": "ZZFD",
        "name": "Zephyr Foods Corp.",
        "nameZh": "和风食品",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "公司持续回购股票并维持分红",
       "killCondition": "暂停回购或削减分红",
       "relation": "uncertain",
       "headline": 0.55,
       "probabilities": {
        "relevant": 0.93,
        "against": 0.55,
        "contradicts": 0.22,
        "killMet": 0.31,
        "supports": 0.18
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000004",
        "instrumentId": "us:ZZFD",
        "title": "8-K: Quarterly dividend and share repurchase update",
        "formType": "8-K",
        "publishedAt": "2026-10-29T13:02:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000004/zzfd-8k.htm"
       },
       "evidence": {
        "kind": "passage",
        "text": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
        "passageText": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
        "sentenceStart": null,
        "sentenceEnd": null,
        "filePart": "主文档"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      },
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z5",
       "thesisId": "01JC8Z5V3Q00000000000063A4",
       "thesisVersion": 1,
       "thesisCurrentVersion": 2,
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "云业务收入保持两位数增长",
       "killCondition": "云业务收入同比增速低于 10%",
       "relation": "uncertain",
       "headline": 0.42,
       "probabilities": {
        "relevant": 0.58,
        "against": 0.42,
        "contradicts": 0.2,
        "killMet": 0.35,
        "supports": 0.1
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000006",
        "instrumentId": "us:ZZCL",
        "title": "6-K: Notice of Extraordinary General Meeting",
        "formType": "6-K",
        "publishedAt": "2026-10-28T09:45:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000006/zzcl-6k.htm"
       },
       "evidence": {
        "kind": "title",
        "text": "6-K: Notice of Extraordinary General Meeting",
        "passageText": "6-K: Notice of Extraordinary General Meeting",
        "sentenceStart": null,
        "sentenceEnd": null,
        "filePart": "标题"
       },
       "contentStatus": "title_only",
       "createdAt": "2026-11-02T00:31:12Z",
       "action": null
      }
     ],
     "processed": [
      {
       "decisionId": "01JC8Z5V3Q00000000000094Z6",
       "thesisId": "01JC8Z5V3Q00000000000063A5",
       "thesisVersion": 1,
       "thesisCurrentVersion": 1,
       "instrument": {
        "instrumentId": "us:ZZBK",
        "market": "us",
        "symbol": "ZZBK",
        "name": "Zinc Bay Bancorp",
        "nameZh": "锌湾银行",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "thesisStatement": "存款成本保持稳定，净息差不收窄",
       "killCondition": null,
       "relation": "weaken",
       "headline": 0.72,
       "probabilities": {
        "relevant": 0.96,
        "against": 0.72,
        "contradicts": 0.3,
        "killMet": null,
        "supports": 0.08
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "questionSetVersion": "qs-2026-11-02.2",
       "event": {
        "eventId": "us:0009990001-26-000005",
        "instrumentId": "us:ZZBK",
        "title": "8-K: Third quarter 2026 net interest margin",
        "formType": "8-K",
        "publishedAt": "2026-10-27T21:15:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000005/zzbk-ex991.htm"
       },
       "evidence": {
        "kind": "sentence",
        "text": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter.",
        "passageText": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
        "sentenceStart": 0,
        "sentenceEnd": 131,
        "filePart": "EX-99.1"
       },
       "contentStatus": "full_text",
       "createdAt": "2026-10-28T00:20:00Z",
       "action": {
        "action": "still_valid",
        "note": "只收窄了 3 个基点，管理层预计稳定",
        "actedAt": "2026-10-28T02:40:00Z"
       }
      }
     ],
     "lastScan": {
      "runId": "01JC8Z5V3Q000000000000C6M1",
      "status": "succeeded",
      "finishedAt": "2026-11-02T00:31:12Z",
      "stats": {
       "instruments": 4,
       "skippedNoThesis": 2,
       "filings": 6,
       "passages": 17,
       "decisions": 21
      },
      "error": null
     },
     "dataStatus": {
      "market": "us",
      "marketState": "closed",
      "nextOpenAt": "2026-11-02T14:30:00Z",
      "source": {
       "name": "SEC EDGAR",
       "state": "down",
       "lastSuccessAt": "2026-11-02T00:31:12Z",
       "message": "当前离线"
      },
      "engine": {
       "active": "jev_direct",
       "modelId": "jev-1.14.0",
       "state": "ok"
      },
      "budget": {
       "usedTokens": 18420,
       "limitTokens": 2000000,
       "resetAt": "2026-11-03T00:00:00Z"
      },
      "offline": true
     },
     "setup": {
      "holdings": 6,
      "activeTheses": 5,
      "scannableInstruments": 4
     }
    }
   }
  },
  "decision.get": {
   "overturn": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z1"
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z1",
     "thesisId": "01JC8Z5V3Q00000000000063A1",
     "thesisVersion": 2,
     "thesisCurrentVersion": 2,
     "instrument": {
      "instrumentId": "us:ZZAR",
      "market": "us",
      "symbol": "ZZAR",
      "name": "Zenith Arc Robotics Inc.",
      "nameZh": "天顶弧机器人",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "控股股东长期持股，不会大幅减持",
     "killCondition": "控股股东减持超过 2%",
     "relation": "overturn",
     "headline": 0.93,
     "probabilities": {
      "relevant": 0.97,
      "against": 0.89,
      "contradicts": 0.84,
      "killMet": 0.93,
      "supports": 0.03
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000001",
      "instrumentId": "us:ZZAR",
      "title": "8-K: Other Events — Completed sale by controlling stockholder",
      "formType": "8-K",
      "publishedAt": "2026-10-30T20:12:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000001/zzar-8k.htm"
     },
     "evidence": {
      "kind": "sentence",
      "text": "On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering.",
      "passageText": "Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering. Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
      "sentenceStart": 24,
      "sentenceEnd": 265,
      "filePart": "主文档"
     },
     "contentStatus": "full_text",
     "createdAt": "2026-11-02T00:31:12Z",
     "action": null,
     "actions": [],
     "thesisIsLatest": true
    }
   },
   "weaken": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z3"
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z3",
     "thesisId": "01JC8Z5V3Q00000000000063A2",
     "thesisVersion": 1,
     "thesisCurrentVersion": 1,
     "instrument": {
      "instrumentId": "us:ZZAR",
      "market": "us",
      "symbol": "ZZAR",
      "name": "Zenith Arc Robotics Inc.",
      "nameZh": "天顶弧机器人",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "Management keeps R&D spending above 15% of revenue",
     "killCondition": null,
     "relation": "weaken",
     "headline": 0.74,
     "probabilities": {
      "relevant": 0.95,
      "against": 0.74,
      "contradicts": 0.41,
      "killMet": null,
      "supports": 0.06
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000003",
      "instrumentId": "us:ZZAR",
      "title": "8-K: Results of Operations — Third Quarter 2026",
      "formType": "8-K",
      "publishedAt": "2026-10-29T20:05:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000003/zzar-ex991.htm"
     },
     "evidence": {
      "kind": "sentence",
      "text": "Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter.",
      "passageText": "Zenith Arc Robotics reported third quarter revenue of $214.6 million, up 9% from a year earlier. Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter. The Company said it is prioritizing near-term profitability and has paused two early-stage programs.",
      "sentenceStart": 97,
      "sentenceEnd": 248,
      "filePart": "EX-99.1"
     },
     "contentStatus": "full_text",
     "createdAt": "2026-11-02T00:31:12Z",
     "action": null,
     "actions": [],
     "thesisIsLatest": true
    }
   },
   "uncertain": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z4"
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z4",
     "thesisId": "01JC8Z5V3Q00000000000063A3",
     "thesisVersion": 1,
     "thesisCurrentVersion": 1,
     "instrument": {
      "instrumentId": "us:ZZFD",
      "market": "us",
      "symbol": "ZZFD",
      "name": "Zephyr Foods Corp.",
      "nameZh": "和风食品",
      "exchange": "NYSE",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "公司持续回购股票并维持分红",
     "killCondition": "暂停回购或削减分红",
     "relation": "uncertain",
     "headline": 0.55,
     "probabilities": {
      "relevant": 0.93,
      "against": 0.55,
      "contradicts": 0.22,
      "killMet": 0.31,
      "supports": 0.18
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000004",
      "instrumentId": "us:ZZFD",
      "title": "8-K: Quarterly dividend and share repurchase update",
      "formType": "8-K",
      "publishedAt": "2026-10-29T13:02:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000004/zzfd-8k.htm"
     },
     "evidence": {
      "kind": "passage",
      "text": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
      "passageText": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
      "sentenceStart": null,
      "sentenceEnd": null,
      "filePart": "主文档"
     },
     "contentStatus": "full_text",
     "createdAt": "2026-11-02T00:31:12Z",
     "action": null,
     "actions": [],
     "thesisIsLatest": true
    }
   },
   "title_only": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z5"
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z5",
     "thesisId": "01JC8Z5V3Q00000000000063A4",
     "thesisVersion": 1,
     "thesisCurrentVersion": 2,
     "instrument": {
      "instrumentId": "us:ZZCL",
      "market": "us",
      "symbol": "ZZCL",
      "name": "Zhongzhi Cloud Ltd.",
      "nameZh": "众智云",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "云业务收入保持两位数增长",
     "killCondition": "云业务收入同比增速低于 10%",
     "relation": "uncertain",
     "headline": 0.42,
     "probabilities": {
      "relevant": 0.58,
      "against": 0.42,
      "contradicts": 0.2,
      "killMet": 0.35,
      "supports": 0.1
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000006",
      "instrumentId": "us:ZZCL",
      "title": "6-K: Notice of Extraordinary General Meeting",
      "formType": "6-K",
      "publishedAt": "2026-10-28T09:45:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000006/zzcl-6k.htm"
     },
     "evidence": {
      "kind": "title",
      "text": "6-K: Notice of Extraordinary General Meeting",
      "passageText": "6-K: Notice of Extraordinary General Meeting",
      "sentenceStart": null,
      "sentenceEnd": null,
      "filePart": "标题"
     },
     "contentStatus": "title_only",
     "createdAt": "2026-11-02T00:31:12Z",
     "action": null,
     "actions": [],
     "thesisIsLatest": true
    }
   },
   "processed": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z6"
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z6",
     "thesisId": "01JC8Z5V3Q00000000000063A5",
     "thesisVersion": 1,
     "thesisCurrentVersion": 1,
     "instrument": {
      "instrumentId": "us:ZZBK",
      "market": "us",
      "symbol": "ZZBK",
      "name": "Zinc Bay Bancorp",
      "nameZh": "锌湾银行",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "存款成本保持稳定，净息差不收窄",
     "killCondition": null,
     "relation": "weaken",
     "headline": 0.72,
     "probabilities": {
      "relevant": 0.96,
      "against": 0.72,
      "contradicts": 0.3,
      "killMet": null,
      "supports": 0.08
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000005",
      "instrumentId": "us:ZZBK",
      "title": "8-K: Third quarter 2026 net interest margin",
      "formType": "8-K",
      "publishedAt": "2026-10-27T21:15:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000005/zzbk-ex991.htm"
     },
     "evidence": {
      "kind": "sentence",
      "text": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter.",
      "passageText": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
      "sentenceStart": 0,
      "sentenceEnd": 131,
      "filePart": "EX-99.1"
     },
     "contentStatus": "full_text",
     "createdAt": "2026-10-28T00:20:00Z",
     "action": {
      "action": "still_valid",
      "note": "只收窄了 3 个基点，管理层预计稳定",
      "actedAt": "2026-10-28T02:40:00Z"
     },
     "actions": [
      {
       "action": "still_valid",
       "note": "只收窄了 3 个基点，管理层预计稳定",
       "actedAt": "2026-10-28T02:40:00Z"
      }
     ],
     "thesisIsLatest": true
    }
   },
   "not_found": {
    "params": {
     "decisionId": "01JC8Z5V3QZZZZZZZZZZZZZZZZ"
    },
    "error": {
     "code": "NOT_FOUND",
     "message": "没有找到这条判定",
     "data": {
      "retryable": false
     }
    }
   }
  },
  "decision.act": {
   "still_valid": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z1",
     "action": "still_valid",
     "note": null
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z1",
     "thesisId": "01JC8Z5V3Q00000000000063A1",
     "thesisVersion": 2,
     "thesisCurrentVersion": 2,
     "instrument": {
      "instrumentId": "us:ZZAR",
      "market": "us",
      "symbol": "ZZAR",
      "name": "Zenith Arc Robotics Inc.",
      "nameZh": "天顶弧机器人",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "控股股东长期持股，不会大幅减持",
     "killCondition": "控股股东减持超过 2%",
     "relation": "overturn",
     "headline": 0.93,
     "probabilities": {
      "relevant": 0.97,
      "against": 0.89,
      "contradicts": 0.84,
      "killMet": 0.93,
      "supports": 0.03
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000001",
      "instrumentId": "us:ZZAR",
      "title": "8-K: Other Events — Completed sale by controlling stockholder",
      "formType": "8-K",
      "publishedAt": "2026-10-30T20:12:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000001/zzar-8k.htm"
     },
     "evidence": {
      "kind": "sentence",
      "text": "On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering.",
      "passageText": "Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the \"Company\") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas completed the sale of 4.5% of the Company's outstanding common stock in a registered secondary offering. Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
      "sentenceStart": 24,
      "sentenceEnd": 265,
      "filePart": "主文档"
     },
     "contentStatus": "full_text",
     "createdAt": "2026-11-02T00:31:12Z",
     "action": {
      "action": "still_valid",
      "note": null,
      "actedAt": "2026-11-02T00:37:00Z"
     }
    }
   }
  },
  "decision.reopen": {
   "ok": {
    "params": {
     "decisionId": "01JC8Z5V3Q00000000000094Z6"
    },
    "result": {
     "decisionId": "01JC8Z5V3Q00000000000094Z6",
     "thesisId": "01JC8Z5V3Q00000000000063A5",
     "thesisVersion": 1,
     "thesisCurrentVersion": 1,
     "instrument": {
      "instrumentId": "us:ZZBK",
      "market": "us",
      "symbol": "ZZBK",
      "name": "Zinc Bay Bancorp",
      "nameZh": "锌湾银行",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "thesisStatement": "存款成本保持稳定，净息差不收窄",
     "killCondition": null,
     "relation": "weaken",
     "headline": 0.72,
     "probabilities": {
      "relevant": 0.96,
      "against": 0.72,
      "contradicts": 0.3,
      "killMet": null,
      "supports": 0.08
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "questionSetVersion": "qs-2026-11-02.2",
     "event": {
      "eventId": "us:0009990001-26-000005",
      "instrumentId": "us:ZZBK",
      "title": "8-K: Third quarter 2026 net interest margin",
      "formType": "8-K",
      "publishedAt": "2026-10-27T21:15:00Z",
      "url": "https://www.sec.gov/Archives/edgar/data/9990001/000999000126000005/zzbk-ex991.htm"
     },
     "evidence": {
      "kind": "sentence",
      "text": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter.",
      "passageText": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
      "sentenceStart": 0,
      "sentenceEnd": 131,
      "filePart": "EX-99.1"
     },
     "contentStatus": "full_text",
     "createdAt": "2026-10-28T00:20:00Z",
     "action": null
    }
   }
  },
  "scan.start": {
   "ok": {
    "params": {
     "market": "us"
    },
    "result": {
     "runId": "01JC8Z5V3Q000000000000C6M5"
    }
   },
   "config_required": {
    "params": {
     "market": "us"
    },
    "error": {
     "code": "CONFIG_REQUIRED",
     "message": "请先填写 Jev 密钥和 SEC 联系邮箱",
     "data": {
      "retryable": false,
      "missing": [
       "jevKey",
       "secEmail"
      ]
     }
    }
   },
   "conflict": {
    "params": {
     "market": "us"
    },
    "error": {
     "code": "CONFLICT",
     "message": "扫描正在进行",
     "data": {
      "retryable": false
     }
    }
   },
   "budget": {
    "params": {
     "market": "us"
    },
    "error": {
     "code": "BUDGET_EXCEEDED",
     "message": "今日预算已用完（2,000,000 / 2,000,000 tokens），明天 08:00 后可继续",
     "data": {
      "retryable": false,
      "usedTokens": 2000000,
      "limitTokens": 2000000
     }
    }
   },
   "rate_limited": {
    "params": {
     "market": "us"
    },
    "error": {
     "code": "RATE_LIMITED",
     "message": "请求过于频繁，约 20 秒后重试",
     "data": {
      "retryable": true,
      "retryAfterSec": 20,
      "source": "SEC EDGAR"
     }
    }
   },
   "unauthenticated": {
    "params": {
     "market": "us"
    },
    "error": {
     "code": "UNAUTHENTICATED",
     "message": "Jev 密钥无效（401）。请重新填写 Jev 密钥。",
     "data": {
      "retryable": false
     }
    }
   },
   "engine_unavailable": {
    "params": {
     "market": "us"
    },
    "error": {
     "code": "ENGINE_UNAVAILABLE",
     "message": "JEVDB 扩展无法加载。请在设置里把引擎改为“自动”或“Jev 直连”。",
     "data": {
      "retryable": false,
      "engine": "jevdb"
     }
    }
   }
  },
  "scan.cancel": {
   "ok": {
    "params": {
     "runId": "01JC8Z5V3Q000000000000C6M5"
    },
    "result": {
     "ok": true
    }
   }
  },
  "scan.status": {
   "running": {
    "params": {
     "runId": "01JC8Z5V3Q000000000000C6M5"
    },
    "result": {
     "runId": "01JC8Z5V3Q000000000000C6M5",
     "trigger": "manual",
     "market": "us",
     "status": "running",
     "windowStart": "2026-10-26T00:00:00Z",
     "windowEnd": "2026-11-02T00:30:41Z",
     "stats": {
      "instruments": 4,
      "skippedNoThesis": 2,
      "filings": 6,
      "passages": 17,
      "decisions": 9,
      "cachedDecisions": 0,
      "requests": 9,
      "inputTokens": 9800,
      "estCostUsd": "0.000412",
      "durationMs": 40000
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "startedAt": "2026-11-02T00:34:20Z",
     "finishedAt": null,
     "error": null,
     "batchSummary": {
      "total": 17,
      "succeeded": 9,
      "failed": 0,
      "pending": 8
     }
    }
   },
   "done": {
    "params": {
     "runId": "01JC8Z5V3Q000000000000C6M1"
    },
    "result": {
     "runId": "01JC8Z5V3Q000000000000C6M1",
     "trigger": "manual",
     "market": "us",
     "status": "succeeded",
     "windowStart": "2026-10-26T00:00:00Z",
     "windowEnd": "2026-11-02T00:30:41Z",
     "stats": {
      "instruments": 4,
      "skippedNoThesis": 2,
      "filings": 6,
      "passages": 17,
      "decisions": 21,
      "cachedDecisions": 0,
      "requests": 17,
      "inputTokens": 18420,
      "estCostUsd": "0.000774",
      "durationMs": 31000
     },
     "engine": "jev_direct",
     "modelId": "jev-1.14.0",
     "startedAt": "2026-11-02T00:30:41Z",
     "finishedAt": "2026-11-02T00:31:12Z",
     "error": null,
     "batchSummary": {
      "total": 17,
      "succeeded": 17,
      "failed": 0,
      "pending": 0
     }
    }
   }
  },
  "scan.history": {
   "default": {
    "params": {
     "limit": 20
    },
    "result": {
     "items": [
      {
       "runId": "01JC8Z5V3Q000000000000C6M1",
       "trigger": "manual",
       "market": "us",
       "status": "succeeded",
       "windowStart": "2026-10-26T00:00:00Z",
       "windowEnd": "2026-11-02T00:30:41Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 6,
        "passages": 17,
        "decisions": 21,
        "cachedDecisions": 0,
        "requests": 17,
        "inputTokens": 18420,
        "estCostUsd": "0.000774",
        "durationMs": 31000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-11-02T00:30:41Z",
       "finishedAt": "2026-11-02T00:31:12Z",
       "error": null,
       "batchSummary": {
        "total": 17,
        "succeeded": 17,
        "failed": 0,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "trigger": "manual",
       "market": "us",
       "status": "partial",
       "windowStart": "2026-10-28T00:00:00Z",
       "windowEnd": "2026-10-31T09:10:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 2,
        "passages": 5,
        "decisions": 6,
        "cachedDecisions": 0,
        "requests": 5,
        "inputTokens": 6110,
        "estCostUsd": "0.000257",
        "durationMs": 78000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-31T09:10:02Z",
       "finishedAt": "2026-10-31T09:11:20Z",
       "error": {
        "code": "MODEL_ERROR",
        "message": "1 个批次判定失败，已保留其余结果，下次扫描会自动重试"
       },
       "batchSummary": {
        "total": 5,
        "succeeded": 4,
        "failed": 1,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M3",
       "trigger": "manual",
       "market": "us",
       "status": "succeeded",
       "windowStart": "2026-10-26T00:00:00Z",
       "windowEnd": "2026-10-28T00:15:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 3,
        "passages": 6,
        "decisions": 7,
        "cachedDecisions": 0,
        "requests": 6,
        "inputTokens": 7240,
        "estCostUsd": "0.000304",
        "durationMs": 38000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-28T00:15:10Z",
       "finishedAt": "2026-10-28T00:15:48Z",
       "error": null,
       "batchSummary": {
        "total": 6,
        "succeeded": 6,
        "failed": 0,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M4",
       "trigger": "manual",
       "market": "us",
       "status": "cancelled",
       "windowStart": "2026-10-19T00:00:00Z",
       "windowEnd": "2026-10-26T01:02:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 1,
        "passages": 1,
        "decisions": 0,
        "cachedDecisions": 0,
        "requests": 0,
        "inputTokens": 0,
        "estCostUsd": "0.000000",
        "durationMs": 9000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-26T01:02:00Z",
       "finishedAt": "2026-10-26T01:02:09Z",
       "error": null,
       "batchSummary": {
        "total": 8,
        "succeeded": 0,
        "failed": 0,
        "pending": 8
       }
      }
     ],
     "nextCursor": null,
     "budget": {
      "usedTokens": 18420,
      "limitTokens": 2000000,
      "resetAt": "2026-11-03T00:00:00Z"
     }
    }
   },
   "empty": {
    "params": {
     "limit": 20
    },
    "result": {
     "items": [],
     "nextCursor": null,
     "budget": {
      "usedTokens": 18420,
      "limitTokens": 2000000,
      "resetAt": "2026-11-03T00:00:00Z"
     }
    }
   },
   "budget_exhausted": {
    "params": {
     "limit": 20
    },
    "result": {
     "items": [
      {
       "runId": "01JC8Z5V3Q000000000000C6M1",
       "trigger": "manual",
       "market": "us",
       "status": "succeeded",
       "windowStart": "2026-10-26T00:00:00Z",
       "windowEnd": "2026-11-02T00:30:41Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 6,
        "passages": 17,
        "decisions": 21,
        "cachedDecisions": 0,
        "requests": 17,
        "inputTokens": 18420,
        "estCostUsd": "0.000774",
        "durationMs": 31000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-11-02T00:30:41Z",
       "finishedAt": "2026-11-02T00:31:12Z",
       "error": null,
       "batchSummary": {
        "total": 17,
        "succeeded": 17,
        "failed": 0,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "trigger": "manual",
       "market": "us",
       "status": "partial",
       "windowStart": "2026-10-28T00:00:00Z",
       "windowEnd": "2026-10-31T09:10:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 2,
        "passages": 5,
        "decisions": 6,
        "cachedDecisions": 0,
        "requests": 5,
        "inputTokens": 6110,
        "estCostUsd": "0.000257",
        "durationMs": 78000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-31T09:10:02Z",
       "finishedAt": "2026-10-31T09:11:20Z",
       "error": {
        "code": "MODEL_ERROR",
        "message": "1 个批次判定失败，已保留其余结果，下次扫描会自动重试"
       },
       "batchSummary": {
        "total": 5,
        "succeeded": 4,
        "failed": 1,
        "pending": 0
       }
      }
     ],
     "nextCursor": null,
     "budget": {
      "usedTokens": 2000000,
      "limitTokens": 2000000,
      "resetAt": "2026-11-03T00:00:00Z"
     }
    }
   },
   "running": {
    "params": {
     "limit": 20
    },
    "result": {
     "items": [
      {
       "runId": "01JC8Z5V3Q000000000000C6M5",
       "trigger": "manual",
       "market": "us",
       "status": "running",
       "windowStart": "2026-10-26T00:00:00Z",
       "windowEnd": "2026-11-02T00:30:41Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 6,
        "passages": 17,
        "decisions": 9,
        "cachedDecisions": 0,
        "requests": 9,
        "inputTokens": 9800,
        "estCostUsd": "0.000412",
        "durationMs": 40000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-11-02T00:34:20Z",
       "finishedAt": null,
       "error": null,
       "batchSummary": {
        "total": 17,
        "succeeded": 9,
        "failed": 0,
        "pending": 8
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M1",
       "trigger": "manual",
       "market": "us",
       "status": "succeeded",
       "windowStart": "2026-10-26T00:00:00Z",
       "windowEnd": "2026-11-02T00:30:41Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 6,
        "passages": 17,
        "decisions": 21,
        "cachedDecisions": 0,
        "requests": 17,
        "inputTokens": 18420,
        "estCostUsd": "0.000774",
        "durationMs": 31000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-11-02T00:30:41Z",
       "finishedAt": "2026-11-02T00:31:12Z",
       "error": null,
       "batchSummary": {
        "total": 17,
        "succeeded": 17,
        "failed": 0,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "trigger": "manual",
       "market": "us",
       "status": "partial",
       "windowStart": "2026-10-28T00:00:00Z",
       "windowEnd": "2026-10-31T09:10:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 2,
        "passages": 5,
        "decisions": 6,
        "cachedDecisions": 0,
        "requests": 5,
        "inputTokens": 6110,
        "estCostUsd": "0.000257",
        "durationMs": 78000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-31T09:10:02Z",
       "finishedAt": "2026-10-31T09:11:20Z",
       "error": {
        "code": "MODEL_ERROR",
        "message": "1 个批次判定失败，已保留其余结果，下次扫描会自动重试"
       },
       "batchSummary": {
        "total": 5,
        "succeeded": 4,
        "failed": 1,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M3",
       "trigger": "manual",
       "market": "us",
       "status": "succeeded",
       "windowStart": "2026-10-26T00:00:00Z",
       "windowEnd": "2026-10-28T00:15:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 3,
        "passages": 6,
        "decisions": 7,
        "cachedDecisions": 0,
        "requests": 6,
        "inputTokens": 7240,
        "estCostUsd": "0.000304",
        "durationMs": 38000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-28T00:15:10Z",
       "finishedAt": "2026-10-28T00:15:48Z",
       "error": null,
       "batchSummary": {
        "total": 6,
        "succeeded": 6,
        "failed": 0,
        "pending": 0
       }
      },
      {
       "runId": "01JC8Z5V3Q000000000000C6M4",
       "trigger": "manual",
       "market": "us",
       "status": "cancelled",
       "windowStart": "2026-10-19T00:00:00Z",
       "windowEnd": "2026-10-26T01:02:00Z",
       "stats": {
        "instruments": 4,
        "skippedNoThesis": 2,
        "filings": 1,
        "passages": 1,
        "decisions": 0,
        "cachedDecisions": 0,
        "requests": 0,
        "inputTokens": 0,
        "estCostUsd": "0.000000",
        "durationMs": 9000
       },
       "engine": "jev_direct",
       "modelId": "jev-1.14.0",
       "startedAt": "2026-10-26T01:02:00Z",
       "finishedAt": "2026-10-26T01:02:09Z",
       "error": null,
       "batchSummary": {
        "total": 8,
        "succeeded": 0,
        "failed": 0,
        "pending": 8
       }
      }
     ],
     "nextCursor": null,
     "budget": {
      "usedTokens": 18420,
      "limitTokens": 2000000,
      "resetAt": "2026-11-03T00:00:00Z"
     }
    }
   }
  },
  "scan.detail": {
   "with_failures": {
    "params": {
     "runId": "01JC8Z5V3Q000000000000C6M2"
    },
    "result": {
     "run": {
      "runId": "01JC8Z5V3Q000000000000C6M2",
      "trigger": "manual",
      "market": "us",
      "status": "partial",
      "windowStart": "2026-10-28T00:00:00Z",
      "windowEnd": "2026-10-31T09:10:00Z",
      "stats": {
       "instruments": 4,
       "skippedNoThesis": 2,
       "filings": 2,
       "passages": 5,
       "decisions": 6,
       "cachedDecisions": 0,
       "requests": 5,
       "inputTokens": 6110,
       "estCostUsd": "0.000257",
       "durationMs": 78000
      },
      "engine": "jev_direct",
      "modelId": "jev-1.14.0",
      "startedAt": "2026-10-31T09:10:02Z",
      "finishedAt": "2026-10-31T09:11:20Z",
      "error": {
       "code": "MODEL_ERROR",
       "message": "1 个批次判定失败，已保留其余结果，下次扫描会自动重试"
      },
      "batchSummary": {
       "total": 5,
       "succeeded": 4,
       "failed": 1,
       "pending": 0
      }
     },
     "batches": [
      {
       "batchId": "01JC8Z5V3Q000000000000F891",
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "instrumentId": "us:ZZAR",
       "eventId": "us:0009990001-26-000003",
       "eventTitle": "8-K: Results of Operations — Third Quarter 2026",
       "status": "succeeded",
       "attempts": 1,
       "error": null,
       "passages": 2,
       "decisions": 4,
       "inputTokens": 2300
      },
      {
       "batchId": "01JC8Z5V3Q000000000000F892",
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "instrumentId": "us:ZZFD",
       "eventId": "us:0009990001-26-000004",
       "eventTitle": "8-K: Quarterly dividend and share repurchase update",
       "status": "succeeded",
       "attempts": 1,
       "error": null,
       "passages": 1,
       "decisions": 1,
       "inputTokens": 1200
      },
      {
       "batchId": "01JC8Z5V3Q000000000000F893",
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "instrumentId": "us:ZZCL",
       "eventId": "us:0009990001-26-000006",
       "eventTitle": "6-K: Notice of Extraordinary General Meeting",
       "status": "failed",
       "attempts": 3,
       "error": {
        "code": "MODEL_ERROR",
        "message": "Jev 返回 529（服务过载），已重试 3 次"
       },
       "passages": 1,
       "decisions": 0,
       "inputTokens": 0
      },
      {
       "batchId": "01JC8Z5V3Q000000000000F894",
       "runId": "01JC8Z5V3Q000000000000C6M2",
       "instrumentId": "us:ZZBK",
       "eventId": "us:0009990001-26-000005",
       "eventTitle": "8-K: Third quarter 2026 net interest margin",
       "status": "succeeded",
       "attempts": 1,
       "error": null,
       "passages": 1,
       "decisions": 1,
       "inputTokens": 900
      }
     ]
    }
   }
  },
  "scan.retryBatch": {
   "ok": {
    "params": {
     "batchId": "01JC8Z5V3Q000000000000F893"
    },
    "result": {
     "batchId": "01JC8Z5V3Q000000000000F893",
     "runId": "01JC8Z5V3Q000000000000C6M2",
     "instrumentId": "us:ZZCL",
     "eventId": "us:0009990001-26-000006",
     "eventTitle": "6-K: Notice of Extraordinary General Meeting",
     "status": "succeeded",
     "attempts": 4,
     "error": null,
     "passages": 1,
     "decisions": 1,
     "inputTokens": 1000
    }
   },
   "model_error": {
    "params": {
     "batchId": "01JC8Z5V3Q000000000000F893"
    },
    "error": {
     "code": "MODEL_ERROR",
     "message": "Jev 暂时不可用（529），稍后会自动重试。",
     "data": {
      "retryable": true,
      "status": 529
     }
    }
   },
   "timeout": {
    "params": {
     "batchId": "01JC8Z5V3Q000000000000F893"
    },
    "error": {
     "code": "TIMEOUT",
     "message": "请求超时，请重试。",
     "data": {
      "retryable": true
     }
    }
   },
   "internal": {
    "params": {
     "batchId": "01JC8Z5V3Q000000000000F893"
    },
    "error": {
     "code": "INTERNAL",
     "message": "发生了未预期的错误，错误编号 r-17-k3j9。",
     "data": {
      "retryable": true,
      "requestId": "r-17-k3j9"
     }
    }
   }
  },
  "paper.accounts": {
   "default": {
    "params": {},
    "result": {
     "items": [
      {
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "name": "回放账户 A",
       "baseCurrency": "USD",
       "initialCash": "100000.0000",
       "startDate": "2026-09-01",
       "clockDate": "2026-10-14",
       "createdAt": "2026-10-30T02:00:00Z"
      }
     ]
    }
   },
   "empty": {
    "params": {},
    "result": {
     "items": []
    }
   }
  },
  "paper.createAccount": {
   "ok": {
    "params": {
     "name": "回放账户 A",
     "initialCash": "100000.00",
     "startDate": "2026-09-01"
    },
    "result": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "name": "回放账户 A",
     "baseCurrency": "USD",
     "initialCash": "100000.0000",
     "startDate": "2026-09-01",
     "clockDate": "2026-10-14",
     "createdAt": "2026-10-30T02:00:00Z"
    }
   }
  },
  "paper.portfolio": {
   "default": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1"
    },
    "result": {
     "account": {
      "accountId": "01JC8Z5V3Q000000000000J9Y1",
      "name": "回放账户 A",
      "baseCurrency": "USD",
      "initialCash": "100000.0000",
      "startDate": "2026-09-01",
      "clockDate": "2026-10-14",
      "createdAt": "2026-10-30T02:00:00Z"
     },
     "cash": "93026.5150",
     "reservedCash": "2841.4200",
     "availableCash": "90185.0950",
     "positions": [
      {
       "instrument": {
        "instrumentId": "us:ZZFD",
        "market": "us",
        "symbol": "ZZFD",
        "name": "Zephyr Foods Corp.",
        "nameZh": "和风食品",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "quantity": 200,
       "sellableQuantity": 200,
       "avgCost": "22.411200",
       "lastClose": 22.95,
       "marketValue": "4590.0000",
       "unrealizedPnl": "107.7600",
       "unrealizedPnlPct": 0.024
      },
      {
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "quantity": 50,
       "sellableQuantity": 50,
       "avgCost": "49.824900",
       "lastClose": 51.1,
       "marketValue": "2555.0000",
       "unrealizedPnl": "63.7550",
       "unrealizedPnlPct": 0.0256
      }
     ],
     "equity": "100171.5150",
     "asOf": "2026-10-14",
     "pendingOrders": 1
    }
   },
   "new_account": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y2"
    },
    "result": {
     "account": {
      "accountId": "01JC8Z5V3Q000000000000J9Y2",
      "name": "新账户",
      "baseCurrency": "USD",
      "initialCash": "50000.0000",
      "startDate": "2026-09-01",
      "clockDate": "2026-09-01",
      "createdAt": "2026-10-30T02:00:00Z"
     },
     "cash": "50000.0000",
     "reservedCash": "0.0000",
     "availableCash": "50000.0000",
     "positions": [],
     "equity": "50000.0000",
     "asOf": "2026-09-01",
     "pendingOrders": 0
    }
   }
  },
  "paper.order.place": {
   "pending": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "instrumentId": "us:ZZCL",
     "side": "buy",
     "quantity": 100,
     "orderType": "market_open",
     "idempotencyKey": "idem-004"
    },
    "result": {
     "orderId": "01JC8Z5V3Q000000000000RD84",
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "instrument": {
      "instrumentId": "us:ZZCL",
      "market": "us",
      "symbol": "ZZCL",
      "name": "Zhongzhi Cloud Ltd.",
      "nameZh": "众智云",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "side": "buy",
     "quantity": 100,
     "orderType": "market_open",
     "status": "pending",
     "rejectReason": null,
     "createdClockDate": "2026-10-14",
     "reservedCash": "2841.4200",
     "idempotencyKey": "idem-004",
     "fills": [],
     "estimate": {
      "price": "28.414200",
      "amount": "2841.4200",
      "fee": "0.0000"
     }
    }
   },
   "insufficient_cash": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "instrumentId": "us:ZZAR",
     "side": "buy",
     "quantity": 1800,
     "orderType": "market_open",
     "idempotencyKey": "idem-005"
    },
    "error": {
     "code": "ORDER_REJECTED",
     "message": "资金不足：预计需要 $92,025.99，可用现金 $90,185.10。",
     "data": {
      "retryable": false,
      "reason": "INSUFFICIENT_CASH",
      "required": "92025.9900",
      "available": "90185.0950",
      "orderId": "01JC8Z5V3Q000000000000RD85"
     }
    }
   },
   "insufficient_position": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "instrumentId": "us:ZZCL",
     "side": "sell",
     "quantity": 500,
     "orderType": "market_open",
     "idempotencyKey": "idem-003"
    },
    "error": {
     "code": "ORDER_REJECTED",
     "message": "可卖数量不足：持仓 0 股，要卖出 500 股。",
     "data": {
      "retryable": false,
      "reason": "INSUFFICIENT_POSITION",
      "held": 0,
      "requested": 500,
      "orderId": "01JC8Z5V3Q000000000000RD83"
     }
    }
   }
  },
  "paper.order.cancel": {
   "ok": {
    "params": {
     "orderId": "01JC8Z5V3Q000000000000RD84"
    },
    "result": {
     "orderId": "01JC8Z5V3Q000000000000RD84",
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "instrument": {
      "instrumentId": "us:ZZCL",
      "market": "us",
      "symbol": "ZZCL",
      "name": "Zhongzhi Cloud Ltd.",
      "nameZh": "众智云",
      "exchange": "NASDAQ",
      "currency": "USD",
      "isActive": true
     },
     "side": "buy",
     "quantity": 100,
     "orderType": "market_open",
     "status": "cancelled",
     "rejectReason": null,
     "createdClockDate": "2026-10-14",
     "reservedCash": null,
     "idempotencyKey": "idem-004",
     "fills": [],
     "estimate": {
      "price": "28.414200",
      "amount": "2841.4200",
      "fee": "0.0000"
     }
    }
   }
  },
  "paper.orders": {
   "default": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "limit": 50
    },
    "result": {
     "items": [
      {
       "orderId": "01JC8Z5V3Q000000000000RD84",
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "side": "buy",
       "quantity": 100,
       "orderType": "market_open",
       "status": "pending",
       "rejectReason": null,
       "createdClockDate": "2026-10-14",
       "reservedCash": "2841.4200",
       "idempotencyKey": "idem-004",
       "fills": [],
       "estimate": {
        "price": "28.414200",
        "amount": "2841.4200",
        "fee": "0.0000"
       }
      },
      {
       "orderId": "01JC8Z5V3Q000000000000RD83",
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "side": "sell",
       "quantity": 500,
       "orderType": "market_open",
       "status": "rejected",
       "rejectReason": {
        "code": "INSUFFICIENT_POSITION",
        "message": "可卖数量不足：持仓 0 股，要卖出 500 股。"
       },
       "createdClockDate": "2026-10-13",
       "reservedCash": null,
       "idempotencyKey": "idem-003",
       "fills": [],
       "estimate": null
      },
      {
       "orderId": "01JC8Z5V3Q000000000000RD82",
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "instrument": {
        "instrumentId": "us:ZZAR",
        "market": "us",
        "symbol": "ZZAR",
        "name": "Zenith Arc Robotics Inc.",
        "nameZh": "天顶弧机器人",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "side": "buy",
       "quantity": 50,
       "orderType": "market_open",
       "status": "filled",
       "rejectReason": null,
       "createdClockDate": "2026-09-14",
       "reservedCash": null,
       "idempotencyKey": "idem-002",
       "fills": [
        {
         "fillId": "01JC8Z5V3Q000000000000NBK2",
         "filledOn": "2026-09-15",
         "price": "49.824900",
         "quantity": 50,
         "amount": "2491.2450",
         "fee": "0.0000"
        }
       ],
       "estimate": null
      },
      {
       "orderId": "01JC8Z5V3Q000000000000RD81",
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "instrument": {
        "instrumentId": "us:ZZFD",
        "market": "us",
        "symbol": "ZZFD",
        "name": "Zephyr Foods Corp.",
        "nameZh": "和风食品",
        "exchange": "NYSE",
        "currency": "USD",
        "isActive": true
       },
       "side": "buy",
       "quantity": 200,
       "orderType": "market_open",
       "status": "filled",
       "rejectReason": null,
       "createdClockDate": "2026-09-01",
       "reservedCash": null,
       "idempotencyKey": "idem-001",
       "fills": [
        {
         "fillId": "01JC8Z5V3Q000000000000NBK1",
         "filledOn": "2026-09-02",
         "price": "22.411200",
         "quantity": 200,
         "amount": "4482.2400",
         "fee": "0.0000"
        }
       ],
       "estimate": null
      }
     ],
     "nextCursor": null
    }
   }
  },
  "paper.advance": {
   "filled": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1"
    },
    "result": {
     "clockDate": "2026-10-15",
     "tradingDay": true,
     "filled": [
      {
       "orderId": "01JC8Z5V3Q000000000000RD84",
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "instrument": {
        "instrumentId": "us:ZZCL",
        "market": "us",
        "symbol": "ZZCL",
        "name": "Zhongzhi Cloud Ltd.",
        "nameZh": "众智云",
        "exchange": "NASDAQ",
        "currency": "USD",
        "isActive": true
       },
       "side": "buy",
       "quantity": 100,
       "orderType": "market_open",
       "status": "filled",
       "rejectReason": null,
       "createdClockDate": "2026-10-14",
       "reservedCash": null,
       "idempotencyKey": "idem-004",
       "fills": [
        {
         "fillId": "01JC8Z5V3Q000000000000NBK4",
         "filledOn": "2026-10-15",
         "price": "28.564275",
         "quantity": 100,
         "amount": "2856.4275",
         "fee": "0.0000"
        }
       ],
       "estimate": {
        "price": "28.414200",
        "amount": "2841.4200",
        "fee": "0.0000"
       }
      }
     ],
     "rejected": [],
     "pendingRemaining": 0,
     "portfolio": {
      "account": {
       "accountId": "01JC8Z5V3Q000000000000J9Y1",
       "name": "回放账户 A",
       "baseCurrency": "USD",
       "initialCash": "100000.0000",
       "startDate": "2026-09-01",
       "clockDate": "2026-10-15",
       "createdAt": "2026-10-30T02:00:00Z"
      },
      "cash": "90170.0875",
      "reservedCash": "0.0000",
      "availableCash": "90170.0875",
      "positions": [
       {
        "instrument": {
         "instrumentId": "us:ZZFD",
         "market": "us",
         "symbol": "ZZFD",
         "name": "Zephyr Foods Corp.",
         "nameZh": "和风食品",
         "exchange": "NYSE",
         "currency": "USD",
         "isActive": true
        },
        "quantity": 200,
        "sellableQuantity": 200,
        "avgCost": "22.411200",
        "lastClose": 22.95,
        "marketValue": "4590.0000",
        "unrealizedPnl": "107.7600",
        "unrealizedPnlPct": 0.024
       },
       {
        "instrument": {
         "instrumentId": "us:ZZAR",
         "market": "us",
         "symbol": "ZZAR",
         "name": "Zenith Arc Robotics Inc.",
         "nameZh": "天顶弧机器人",
         "exchange": "NASDAQ",
         "currency": "USD",
         "isActive": true
        },
        "quantity": 50,
        "sellableQuantity": 50,
        "avgCost": "49.824900",
        "lastClose": 51.1,
        "marketValue": "2555.0000",
        "unrealizedPnl": "63.7550",
        "unrealizedPnlPct": 0.0256
       }
      ],
      "equity": "100171.5150",
      "asOf": "2026-10-14",
      "pendingOrders": 0
     }
    }
   },
   "no_price": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1"
    },
    "error": {
     "code": "DATA_INSUFFICIENT",
     "message": "没有 2026-10-16 的行情。请先刷新行情，或选择更早的回放日期。",
     "data": {
      "retryable": false,
      "nextDay": "2026-10-16"
     }
    }
   }
  },
  "paper.reset": {
   "ok": {
    "params": {
     "accountId": "01JC8Z5V3Q000000000000J9Y1",
     "confirmText": "回放账户 A"
    },
    "result": {
     "ok": true
    }
   }
  },
  "risk.compute": {
   "ok": {
    "params": {
     "scope": "holdings",
     "window": "1Y",
     "currency": "USD"
    },
    "result": {
     "asOf": "2026-10-30",
     "window": {
      "label": "1Y",
      "from": "2025-10-30",
      "to": "2026-10-30",
      "observations": 251
     },
     "currency": "USD",
     "annualizedVol": 0.187,
     "maxDrawdown": 0.214,
     "effectiveHoldings": 4.67,
     "topWeights": [
      {
       "instrumentId": "us:ZZFD",
       "symbol": "ZZFD",
       "weight": 0.2782
      },
      {
       "instrumentId": "us:ZZAR",
       "symbol": "ZZAR",
       "weight": 0.2491
      },
      {
       "instrumentId": "us:ZZCL",
       "symbol": "ZZCL",
       "weight": 0.1662
      }
     ],
     "correlation": {
      "instrumentIds": [
       "us:ZZAR",
       "us:ZZFD",
       "us:ZZCL",
       "us:ZZBK",
       "us:ZZEN"
      ],
      "symbols": [
       "ZZAR",
       "ZZFD",
       "ZZCL",
       "ZZBK",
       "ZZEN"
      ],
      "matrix": [
       [
        1.0,
        0.21,
        0.58,
        0.34,
        0.12
       ],
       [
        0.21,
        1.0,
        0.09,
        0.27,
        0.31
       ],
       [
        0.58,
        0.09,
        1.0,
        0.22,
        -0.05
       ],
       [
        0.34,
        0.27,
        0.22,
        1.0,
        0.41
       ],
       [
        0.12,
        0.31,
        -0.05,
        0.41,
        1.0
       ]
      ]
     },
     "svd": {
      "explained": [
       0.46,
       0.22,
       0.15,
       0.1,
       0.07
      ],
      "loadings": [
       {
        "symbol": "ZZAR",
        "value": 0.55
       },
       {
        "symbol": "ZZCL",
        "value": 0.5
       },
       {
        "symbol": "ZZBK",
        "value": 0.47
       },
       {
        "symbol": "ZZEN",
        "value": 0.4
       },
       {
        "symbol": "ZZFD",
        "value": 0.26
       }
      ]
     },
     "conditionNumberRaw": 14.8,
     "conditionNumberShrunk": 9.3,
     "warnings": [],
     "excluded": [
      {
       "instrumentId": "us:ZZMD",
       "symbol": "ZZMD",
       "reason": "只关注，数量为 0，不计入权重"
      }
     ]
    }
   },
   "three_year": {
    "params": {
     "scope": "holdings",
     "window": "3Y",
     "currency": "USD"
    },
    "result": {
     "asOf": "2026-10-30",
     "window": {
      "label": "3Y",
      "from": "2025-10-30",
      "to": "2026-10-30",
      "observations": 251
     },
     "currency": "USD",
     "annualizedVol": 0.187,
     "maxDrawdown": 0.214,
     "effectiveHoldings": 4.67,
     "topWeights": [
      {
       "instrumentId": "us:ZZFD",
       "symbol": "ZZFD",
       "weight": 0.2782
      },
      {
       "instrumentId": "us:ZZAR",
       "symbol": "ZZAR",
       "weight": 0.2491
      },
      {
       "instrumentId": "us:ZZCL",
       "symbol": "ZZCL",
       "weight": 0.1662
      }
     ],
     "correlation": {
      "instrumentIds": [
       "us:ZZAR",
       "us:ZZFD",
       "us:ZZCL",
       "us:ZZBK",
       "us:ZZEN"
      ],
      "symbols": [
       "ZZAR",
       "ZZFD",
       "ZZCL",
       "ZZBK",
       "ZZEN"
      ],
      "matrix": [
       [
        1.0,
        0.21,
        0.58,
        0.34,
        0.12
       ],
       [
        0.21,
        1.0,
        0.09,
        0.27,
        0.31
       ],
       [
        0.58,
        0.09,
        1.0,
        0.22,
        -0.05
       ],
       [
        0.34,
        0.27,
        0.22,
        1.0,
        0.41
       ],
       [
        0.12,
        0.31,
        -0.05,
        0.41,
        1.0
       ]
      ]
     },
     "svd": {
      "explained": [
       0.46,
       0.22,
       0.15,
       0.1,
       0.07
      ],
      "loadings": [
       {
        "symbol": "ZZAR",
        "value": 0.55
       },
       {
        "symbol": "ZZCL",
        "value": 0.5
       },
       {
        "symbol": "ZZBK",
        "value": 0.47
       },
       {
        "symbol": "ZZEN",
        "value": 0.4
       },
       {
        "symbol": "ZZFD",
        "value": 0.26
       }
      ]
     },
     "conditionNumberRaw": 14.8,
     "conditionNumberShrunk": 9.3,
     "warnings": [
      "数据不足三年，实际从 2025-10-30 起"
     ],
     "excluded": [
      {
       "instrumentId": "us:ZZMD",
       "symbol": "ZZMD",
       "reason": "只关注，数量为 0，不计入权重"
      }
     ]
    }
   },
   "single": {
    "params": {
     "scope": "holdings",
     "window": "1Y",
     "currency": "USD"
    },
    "result": {
     "asOf": "2026-10-30",
     "window": {
      "label": "1Y",
      "from": "2025-10-30",
      "to": "2026-10-30",
      "observations": 251
     },
     "currency": "USD",
     "annualizedVol": 0.187,
     "maxDrawdown": 0.214,
     "effectiveHoldings": 1.0,
     "topWeights": [
      {
       "instrumentId": "us:ZZAR",
       "symbol": "ZZAR",
       "weight": 1.0
      }
     ],
     "correlation": {
      "instrumentIds": [
       "us:ZZAR"
      ],
      "symbols": [
       "ZZAR"
      ],
      "matrix": [
       [
        1.0
       ]
      ]
     },
     "svd": {
      "explained": [
       1.0
      ],
      "loadings": [
       {
        "symbol": "ZZAR",
        "value": 1.0
       }
      ]
     },
     "conditionNumberRaw": null,
     "conditionNumberShrunk": null,
     "warnings": [
      "只有 1 只持仓，相关系数与 SVD 没有意义"
     ],
     "excluded": [
      {
       "instrumentId": "us:ZZMD",
       "symbol": "ZZMD",
       "reason": "只关注，数量为 0，不计入权重"
      }
     ]
    }
   },
   "insufficient": {
    "params": {
     "scope": "holdings",
     "window": "6M",
     "currency": "USD"
    },
    "error": {
     "code": "DATA_INSUFFICIENT",
     "message": "样本不足：共同交易日 42 天，至少需要 60 天。",
     "data": {
      "retryable": false,
      "observations": 42,
      "required": 60
     }
    }
   }
  },
  "demo.load": {
   "ok": {
    "params": {},
    "result": {
     "loaded": true,
     "counts": {
      "instruments": 6,
      "holdings": 6,
      "theses": 5,
      "events": 6,
      "decisions": 6,
      "prices": 1500
     }
    }
   }
  },
  "demo.clear": {
   "ok": {
    "params": {},
    "result": {
     "ok": true
    }
   }
  }
 },
 "notifications": {
  "app.ready": {
   "version": "0.1.0",
   "migrationsApplied": 0
  },
  "scan.progress": {
   "runId": "01JC8Z5V3Q000000000000C6M5",
   "market": "us",
   "stage": "decide",
   "done": 9,
   "total": 17,
   "message": "正在判定 ZZCL 的 6-K"
  },
  "scan.finished": {
   "runId": "01JC8Z5V3Q000000000000C6M1",
   "trigger": "manual",
   "market": "us",
   "status": "succeeded",
   "windowStart": "2026-10-26T00:00:00Z",
   "windowEnd": "2026-11-02T00:30:41Z",
   "stats": {
    "instruments": 4,
    "skippedNoThesis": 2,
    "filings": 6,
    "passages": 17,
    "decisions": 21,
    "cachedDecisions": 0,
    "requests": 17,
    "inputTokens": 18420,
    "estCostUsd": "0.000774",
    "durationMs": 31000
   },
   "engine": "jev_direct",
   "modelId": "jev-1.14.0",
   "startedAt": "2026-11-02T00:30:41Z",
   "finishedAt": "2026-11-02T00:31:12Z",
   "error": null,
   "batchSummary": {
    "total": 17,
    "succeeded": 17,
    "failed": 0,
    "pending": 0
   }
  },
  "inbox.updated": {
   "newItems": 3,
   "pendingCount": 3
  },
  "engine.changed": {
   "from": "jevdb",
   "to": "jev_direct",
   "reason": "未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）"
  },
  "source.degraded": {
   "source": "SEC EDGAR",
   "reason": "连续 5 次请求失败，10 分钟后重试"
  },
  "budget.updated": {
   "usedTokens": 18420,
   "limitTokens": 2000000,
   "resetAt": "2026-11-03T00:00:00Z"
  }
 }
};
