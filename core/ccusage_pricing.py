import os
import re
import json
from typing import Optional, Union, Dict, Any, List, Tuple

# Load the compiled databases
try:
    from ccusage_db import LITELLM_PRICING, MODELS_DEV_PRICING, FAST_MULTIPLIER_OVERRIDES
except ImportError:
    LITELLM_PRICING = {}
    MODELS_DEV_PRICING = {}
    FAST_MULTIPLIER_OVERRIDES = {"exact": {}, "normalized_prefix": {}}

MODEL_DATE_SUFFIX_DIGITS = 8
CACHE_CREATE_1H_INPUT_MULTIPLIER = 2.0


class Pricing:
    def __init__(self,
                 input: float,
                 output: float,
                 cache_create: float,
                 cache_read: float,
                 cache_read_explicit: bool,
                 input_above_200k: Optional[float] = None,
                 output_above_200k: Optional[float] = None,
                 cache_create_above_200k: Optional[float] = None,
                 cache_read_above_200k: Optional[float] = None,
                 fast_multiplier: float = 1.0):
        self.input = input
        self.output = output
        self.cache_create = cache_create
        self.cache_read = cache_read
        self.cache_read_explicit = cache_read_explicit
        self.input_above_200k = input_above_200k
        self.output_above_200k = output_above_200k
        self.cache_create_above_200k = cache_create_above_200k
        self.cache_read_above_200k = cache_read_above_200k
        self.fast_multiplier = fast_multiplier

    @classmethod
    def empty(cls):
        return cls(0.0, 0.0, 0.0, 0.0, False, fast_multiplier=1.0)

    def copy(self):
        return Pricing(
            input=self.input,
            output=self.output,
            cache_create=self.cache_create,
            cache_read=self.cache_read,
            cache_read_explicit=self.cache_read_explicit,
            input_above_200k=self.input_above_200k,
            output_above_200k=self.output_above_200k,
            cache_create_above_200k=self.cache_create_above_200k,
            cache_read_above_200k=self.cache_read_above_200k,
            fast_multiplier=self.fast_multiplier
        )


class FastMultiplierOverrides:
    def __init__(self, exact: Dict[str, float], normalized_prefix: Dict[str, float]):
        self.exact = exact
        self.normalized_prefix = normalized_prefix

    @classmethod
    def load(cls):
        return cls(
            exact=FAST_MULTIPLIER_OVERRIDES.get("exact", {}),
            normalized_prefix=FAST_MULTIPLIER_OVERRIDES.get("normalized_prefix", {})
        )

    def multiplier_for(self, model: str) -> Optional[float]:
        if model in self.exact:
            return self.exact[model]
        normalized = model.replace('.', '-').replace('@', '-')
        parts = re.split(r'[/:]', normalized)
        for part in parts:
            for base, multiplier in self.normalized_prefix.items():
                if matches_model_suffix(part, base):
                    return multiplier
        return None


def matches_model_suffix(part: str, base: str) -> bool:
    index = part.rfind(base)
    if index == -1:
        return False
    suffix = part[index:]
    if suffix == base:
        return True
    if len(suffix) > len(base) and suffix[len(base)] == '-':
        return True
    return False


def is_pricing_key_boundary(char: str) -> bool:
    return not (('a' <= char <= 'z') or ('A' <= char <= 'Z') or ('0' <= char <= '9'))


def suffix_starts_with_numeric_model_version(key: str, suffix: str) -> bool:
    if not key or not key[-1].isdigit():
        return False
    if not suffix or suffix[0] not in ('-', '.'):
        return False

    rest = suffix[1:]
    digit_len = 0
    for char in rest:
        if char.isdigit():
            digit_len += 1
        else:
            break

    if digit_len == 0:
        return False

    after_digits = None
    if digit_len < len(rest):
        after_digits = rest[digit_len]

    is_date_suffix = (digit_len == MODEL_DATE_SUFFIX_DIGITS) and (
        after_digits is None or is_pricing_key_boundary(after_digits)
    )
    return not is_date_suffix


def suffix_allows_pricing_key_match(key: str, suffix: str) -> bool:
    if not suffix:
        return True
    separator = suffix[0]
    if not is_pricing_key_boundary(separator):
        return False
    return not suffix_starts_with_numeric_model_version(key, suffix)


def contains_pricing_key(value: str, key: str) -> bool:
    if not key:
        return False
    start = 0
    while True:
        index = value.find(key, start)
        if index == -1:
            break
        # Check boundary before
        before_ok = True
        if index > 0:
            before_char = value[index - 1]
            before_ok = is_pricing_key_boundary(before_char)

        # Check suffix
        suffix = value[index + len(key):]
        if before_ok and suffix_allows_pricing_key_match(key, suffix):
            return True
        start = index + 1
    return False


def normalized_pricing_key(value: str) -> str:
    return value.replace('.', '-').replace('@', '-')


def pricing_key_matches(candidate: str, model: str, normalized_model: str) -> bool:
    if contains_pricing_key(model, candidate) or contains_pricing_key(candidate, model):
        return True
    normalized_candidate = normalized_pricing_key(candidate)
    return (contains_pricing_key(normalized_model, normalized_candidate) or
            contains_pricing_key(normalized_candidate, normalized_model))


def pricing_alias(model: str) -> Optional[str]:
    if model == "gpt-5.3-spark":
        return "gpt-5.3-codex-spark"
    return None


# Global test mock aliases
_test_model_aliases: Dict[str, str] = {}


def resolve_model_name(model: str) -> str:
    # First check test mock aliases
    if model in _test_model_aliases:
        return _test_model_aliases[model]
    if model.endswith("-fast"):
        base = model[:-5]
        if base in _test_model_aliases:
            return _test_model_aliases[base] + "-fast"

    # Then check CCUSAGE_MODEL_ALIASES from env
    env_aliases_str = os.environ.get("CCUSAGE_MODEL_ALIASES", "")
    if env_aliases_str:
        aliases = parse_model_aliases(env_aliases_str)
        if model in aliases and aliases[model]:
            return aliases[model]
        if model.endswith("-fast"):
            base = model[:-5]
            if base in aliases and aliases[base]:
                return aliases[base] + "-fast"
                
    return model


def parse_model_aliases(raw: str) -> Dict[str, str]:
    trimmed = raw.strip()
    if not trimmed:
        return {}
    if trimmed.startswith('{'):
        try:
            return json.loads(trimmed)
        except Exception:
            pass

    stripped = trimmed
    if stripped.startswith('{') and stripped.endswith('}'):
        stripped = stripped[1:-1]

    aliases = {}
    parts = re.split(r'[,;\n]', stripped)
    for part in parts:
        if '=' in part:
            parts_split = part.split('=', 1)
            k = parts_split[0].strip()
            v = parts_split[1].strip()
            if k and v:
                aliases[k] = v
    return aliases


def parse_litellm_pricing(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    if "i" in value and "o" in value:
        try:
            return {
                "input_cost_per_token": float(value["i"]),
                "output_cost_per_token": float(value["o"]),
                "cache_creation_input_token_cost": float(value["cc"]) if value.get("cc") is not None else None,
                "cache_read_input_token_cost": float(value["cr"]) if value.get("cr") is not None else None,
                "input_cost_per_token_above_200k_tokens": float(value["ia"]) if value.get("ia") is not None else None,
                "output_cost_per_token_above_200k_tokens": float(value["oa"]) if value.get("oa") is not None else None,
                "cache_creation_input_token_cost_above_200k_tokens": float(value["cca"]) if value.get("cca") is not None else None,
                "cache_read_input_token_cost_above_200k_tokens": float(value["cra"]) if value.get("cra") is not None else None,
                "max_input_tokens": int(value["ctx"]) if value.get("ctx") is not None else None,
                "fast_multiplier": float(value["fast"]) if value.get("fast") is not None else None
            }
        except (ValueError, TypeError):
            pass

    input_cost = value.get("input_cost_per_token")
    output_cost = value.get("output_cost_per_token")
    if input_cost is None or output_cost is None:
        return None
    try:
        fast_val = None
        provider_specific = value.get("provider_specific_entry")
        if isinstance(provider_specific, dict):
            fast_val_raw = provider_specific.get("fast")
            if fast_val_raw is not None:
                fast_val = float(fast_val_raw)

        return {
            "input_cost_per_token": float(input_cost),
            "output_cost_per_token": float(output_cost),
            "cache_creation_input_token_cost": float(value["cache_creation_input_token_cost"]) if value.get("cache_creation_input_token_cost") is not None else None,
            "cache_read_input_token_cost": float(value["cache_read_input_token_cost"]) if value.get("cache_read_input_token_cost") is not None else None,
            "input_cost_per_token_above_200k_tokens": float(value["input_cost_per_token_above_200k_tokens"]) if value.get("input_cost_per_token_above_200k_tokens") is not None else None,
            "output_cost_per_token_above_200k_tokens": float(value["output_cost_per_token_above_200k_tokens"]) if value.get("output_cost_per_token_above_200k_tokens") is not None else None,
            "cache_creation_input_token_cost_above_200k_tokens": float(value["cache_creation_input_token_cost_above_200k_tokens"]) if value.get("cache_creation_input_token_cost_above_200k_tokens") is not None else None,
            "cache_read_input_token_cost_above_200k_tokens": float(value["cache_read_input_token_cost_above_200k_tokens"]) if value.get("cache_read_input_token_cost_above_200k_tokens") is not None else None,
            "max_input_tokens": int(value["max_input_tokens"]) if value.get("max_input_tokens") is not None else None,
            "fast_multiplier": fast_val
        }
    except (ValueError, TypeError):
        return None


def parse_models_dev_json(json_str: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(json_str)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    def entry_has_models_field(val):
        return isinstance(val, dict) and "models" in val and isinstance(val["models"], dict)

    def entry_has_required_cost(val):
        if not isinstance(val, dict):
            return False
        cost = val.get("cost")
        if not isinstance(cost, dict):
            return False
        return isinstance(cost.get("input"), (int, float)) and isinstance(cost.get("output"), (int, float))

    values = list(data.values())
    if any(entry_has_models_field(v) for v in values):
        if not all(entry_has_models_field(v) for v in values):
            return None
        flat_models = {}
        for provider in data.values():
            for m_key, m_val in provider["models"].items():
                flat_models[m_key] = m_val
        return {"type": "Models", "models": flat_models}

    if not all(entry_has_required_cost(v) for v in values):
        return None

    return {"type": "Models", "models": data}


class PricingMap:
    def __init__(self):
        self.entries: Dict[str, Pricing] = {}
        self.context_limits: Dict[str, int] = {}
        self.enable_models_dev_fallback = False
        self.enable_embedded_models_dev_fallback = False

    @classmethod
    def load_embedded(cls):
        map_obj = cls()
        fast_multiplier_overrides = FastMultiplierOverrides.load()
        
        # Load embedded LiteLLM pricing database
        map_obj.load_json_with_overrides(LITELLM_PRICING, fast_multiplier_overrides)
        
        # Load built-in overrides/configurations
        map_obj.put_builtin_pricing(fast_multiplier_overrides)
        
        # Enable embedded models.dev fallback
        map_obj.enable_embedded_models_dev_fallback = True
        return map_obj

    @classmethod
    def load_with_overrides(cls, offline: bool, log: bool, overrides: Dict[str, dict]):
        map_obj = cls.load_embedded()
        
        # If not offline, normally it fetches over the network in Rust,
        # but in Python we default to embedded or we can replicate it if required.
        # For porting correctness without external network dependencies in tests,
        # we configure fallback flags.
        map_obj.enable_models_dev_fallback = not offline
        map_obj.apply_overrides(overrides)
        return map_obj

    def load_json(self, json_input: Union[str, Dict[str, Any]]) -> int:
        fast_multiplier_overrides = FastMultiplierOverrides.load()
        return self.load_json_with_overrides(json_input, fast_multiplier_overrides)

    def load_json_with_overrides(self, json_input: Union[str, Dict[str, Any]], fast_multiplier_overrides: FastMultiplierOverrides) -> int:
        if isinstance(json_input, str):
            try:
                raw = json.loads(json_input)
            except Exception:
                return 0
        else:
            raw = json_input

        if not isinstance(raw, dict):
            return 0

        loaded_count = 0
        for model, value in raw.items():
            pricing_data = parse_litellm_pricing(value)
            if not pricing_data:
                continue
            input_cost = pricing_data["input_cost_per_token"]
            output_cost = pricing_data["output_cost_per_token"]
            if input_cost is None or output_cost is None:
                continue

            context_limit = pricing_data["max_input_tokens"]
            cache_read_explicit = pricing_data["cache_read_input_token_cost"] is not None
            
            fast_multiplier = pricing_data["fast_multiplier"]
            if fast_multiplier is None:
                fast_multiplier = fast_multiplier_overrides.multiplier_for(model)
            if fast_multiplier is None:
                fast_multiplier = 1.0

            self.entries[model] = Pricing(
                input=input_cost,
                output=output_cost,
                cache_create=pricing_data["cache_creation_input_token_cost"] if pricing_data["cache_creation_input_token_cost"] is not None else input_cost * 1.25,
                cache_read=pricing_data["cache_read_input_token_cost"] if pricing_data["cache_read_input_token_cost"] is not None else input_cost * 0.1,
                cache_read_explicit=cache_read_explicit,
                input_above_200k=pricing_data["input_cost_per_token_above_200k_tokens"],
                output_above_200k=pricing_data["output_cost_per_token_above_200k_tokens"],
                cache_create_above_200k=pricing_data["cache_creation_input_token_cost_above_200k_tokens"],
                cache_read_above_200k=pricing_data["cache_read_input_token_cost_above_200k_tokens"],
                fast_multiplier=fast_multiplier
            )
            if context_limit is not None:
                self.context_limits[model] = context_limit
            loaded_count += 1
        return loaded_count

    def load_models_dev_json_missing(self, json_input: Union[str, Dict[str, Any]]) -> Optional[int]:
        if isinstance(json_input, str):
            parsed = parse_models_dev_json(json_input)
        else:
            # Replicate parse_models_dev_json behavior on already deserialized dictionary
            # Just dump to string and parse to ensure same logic:
            parsed = parse_models_dev_json(json.dumps(json_input))
            
        if parsed is None:
            return None
            
        return self.load_models_dev_models(parsed["models"])

    def load_models_dev_models(self, models: dict) -> int:
        loaded_count = 0
        for model_key, model in models.items():
            model_id = model.get("id") or model_key
            if model_id in self.entries:
                continue
            cost = model.get("cost")
            if not cost:
                continue
            input_val = cost.get("input")
            output_val = cost.get("output")
            if input_val is None or output_val is None:
                continue

            inp = float(input_val) / 1_000_000.0
            out = float(output_val) / 1_000_000.0
            cache_read_explicit = cost.get("cache_read") is not None

            if cost.get("cache_write") is not None:
                cache_create = float(cost["cache_write"]) / 1_000_000.0
            else:
                cache_create = inp * 1.25

            if cost.get("cache_read") is not None:
                cache_read = float(cost["cache_read"]) / 1_000_000.0
            else:
                cache_read = inp * 0.1

            self.entries[model_id] = Pricing(
                input=inp,
                output=out,
                cache_create=cache_create,
                cache_read=cache_read,
                cache_read_explicit=cache_read_explicit,
                input_above_200k=None,
                output_above_200k=None,
                cache_create_above_200k=None,
                cache_read_above_200k=None,
                fast_multiplier=1.0
            )

            limit = model.get("limit")
            if isinstance(limit, dict):
                context = limit.get("context")
                if context is not None:
                    self.context_limits[model_id] = int(context)
            loaded_count += 1
        return loaded_count

    def apply_overrides(self, overrides: Dict[str, dict]):
        for model, override_val in overrides.items():
            self.apply_override(model, override_val)

    def apply_override(self, model: str, override_value: dict):
        base = self.entries.get(model)
        if base is None:
            base = Pricing.empty()

        new_input = override_value.get("input_cost_per_token")
        if new_input is None:
            new_input = base.input

        should_scale = (override_value.get("input_cost_per_token") is not None
                        and base.input > 0.0
                        and not base.cache_read_explicit)
        
        scale = new_input / base.input if should_scale else 1.0

        if override_value.get("cache_creation_input_token_cost") is not None:
            cache_create = override_value["cache_creation_input_token_cost"]
        elif should_scale and base.cache_create > 0.0:
            cache_create = base.cache_create * scale
        else:
            cache_create = base.cache_create

        if override_value.get("cache_read_input_token_cost") is not None:
            cache_read = override_value["cache_read_input_token_cost"]
        elif should_scale and base.cache_read > 0.0:
            cache_read = base.cache_read * scale
        else:
            cache_read = base.cache_read

        if override_value.get("cache_creation_input_token_cost_above_200k_tokens") is not None:
            cache_create_above_200k = override_value["cache_creation_input_token_cost_above_200k_tokens"]
        elif should_scale:
            cache_create_above_200k = base.cache_create_above_200k * scale if base.cache_create_above_200k is not None else None
        else:
            cache_create_above_200k = base.cache_create_above_200k

        if override_value.get("cache_read_input_token_cost_above_200k_tokens") is not None:
            cache_read_above_200k = override_value["cache_read_input_token_cost_above_200k_tokens"]
        elif should_scale:
            cache_read_above_200k = base.cache_read_above_200k * scale if base.cache_read_above_200k is not None else None
        else:
            cache_read_above_200k = base.cache_read_above_200k

        cache_read_explicit = (override_value.get("cache_read_input_token_cost") is not None
                               or base.cache_read_explicit)

        pricing = Pricing(
            input=new_input,
            output=override_value.get("output_cost_per_token") if override_value.get("output_cost_per_token") is not None else base.output,
            cache_create=cache_create,
            cache_read=cache_read,
            cache_read_explicit=cache_read_explicit,
            input_above_200k=override_value.get("input_cost_per_token_above_200k_tokens") if override_value.get("input_cost_per_token_above_200k_tokens") is not None else base.input_above_200k,
            output_above_200k=override_value.get("output_cost_per_token_above_200k_tokens") if override_value.get("output_cost_per_token_above_200k_tokens") is not None else base.output_above_200k,
            cache_create_above_200k=cache_create_above_200k,
            cache_read_above_200k=cache_read_above_200k,
            fast_multiplier=override_value.get("fast_multiplier") if override_value.get("fast_multiplier") is not None else base.fast_multiplier
        )

        self.entries[model] = pricing
        if override_value.get("max_input_tokens") is not None:
            self.context_limits[model] = int(override_value["max_input_tokens"])

    def find(self, model: str) -> Optional[Pricing]:
        alias = resolve_model_name(model)
        
        # Primary lookup
        res = self.find_entry_or_alias(model)
        if res is not None:
            return res
            
        # Resolved alias lookup
        if alias != model:
            res = self.find_entry_or_alias(alias)
            if res is not None:
                return res
                
        # Models dev fallback
        if self.enable_models_dev_fallback:
            dev_map = get_models_dev_pricing_cache()
            if dev_map is not None:
                res = dev_map.find_entry_or_alias(alias)
                if res is not None:
                    return res
                    
        # Embedded models dev fallback
        if self.enable_embedded_models_dev_fallback:
            dev_map = get_embedded_models_dev_pricing()
            res = dev_map.find_entry_or_alias(alias)
            if res is not None:
                return res
                
        return None

    def find_entry_or_alias(self, model: str) -> Optional[Pricing]:
        res = self.find_entry(model)
        if res is not None:
            return res
        alias = pricing_alias(model)
        if alias is not None:
            return self.find_entry(alias)
        return None

    def find_entry(self, model: str) -> Optional[Pricing]:
        if model in self.entries:
            return self.entries[model]

        normalized_model = normalized_pricing_key(model)
        candidates = []
        for candidate, pricing in self.entries.items():
            if pricing_key_matches(candidate, model, normalized_model):
                candidates.append((candidate, pricing))

        if not candidates:
            return None

        # Sort candidates:
        # 1. candidate len descending
        # 2. lexicographically ascending (smaller key wins)
        def key_fn(item):
            k, _ = item
            return (len(k), [-ord(c) for c in k])

        best_candidate, best_pricing = max(candidates, key=key_fn)
        return best_pricing

    def context_limit(self, model: str) -> Optional[int]:
        alias = resolve_model_name(model)
        
        res = self.context_limit_entry_or_alias(model)
        if res is not None:
            return res
            
        if alias != model:
            res = self.context_limit_entry_or_alias(alias)
            if res is not None:
                return res
                
        if self.enable_models_dev_fallback:
            dev_map = get_models_dev_pricing_cache()
            if dev_map is not None:
                res = dev_map.context_limit_entry_or_alias(alias)
                if res is not None:
                    return res
                    
        if self.enable_embedded_models_dev_fallback:
            dev_map = get_embedded_models_dev_pricing()
            res = dev_map.context_limit_entry_or_alias(alias)
            if res is not None:
                return res
                
        return None

    def context_limit_entry_or_alias(self, model: str) -> Optional[int]:
        res = self.context_limit_entry(model)
        if res is not None:
            return res
        alias = pricing_alias(model)
        if alias is not None:
            return self.context_limit_entry(alias)
        return None

    def context_limit_entry(self, model: str) -> Optional[int]:
        if model in self.context_limits:
            return self.context_limits[model]

        normalized_model = normalized_pricing_key(model)
        candidates = []
        for candidate, limit in self.context_limits.items():
            if pricing_key_matches(candidate, model, normalized_model):
                candidates.append((candidate, limit))

        if not candidates:
            return None

        def key_fn(item):
            k, _ = item
            return (len(k), [-ord(c) for c in k])

        best_candidate, best_limit = max(candidates, key=key_fn)
        return best_limit

    def put_builtin_pricing(self, fast_multiplier_overrides: FastMultiplierOverrides):
        def add(model, pricing):
            self.entries[model] = pricing

        add("claude-opus-4-5", Pricing(5e-6, 25e-6, 6.25e-6, 0.5e-6, True))
        add("claude-opus-4-6", Pricing(5e-6, 25e-6, 6.25e-6, 0.5e-6, True,
                                       fast_multiplier=fast_multiplier_overrides.multiplier_for("claude-opus-4-6") or 1.0))
        add("claude-opus-4-7", Pricing(5e-6, 25e-6, 6.25e-6, 0.5e-6, True,
                                       fast_multiplier=fast_multiplier_overrides.multiplier_for("claude-opus-4-7") or 1.0))
        add("claude-opus-4-8", Pricing(5e-6, 25e-6, 6.25e-6, 0.5e-6, True,
                                       fast_multiplier=fast_multiplier_overrides.multiplier_for("claude-opus-4-8") or 1.0))
        add("claude-haiku-4-5", Pricing(1e-6, 5e-6, 1.25e-6, 0.1e-6, True))
        add("claude-opus-4", Pricing(15e-6, 75e-6, 18.75e-6, 1.5e-6, True))
        add("claude-sonnet-4-6", Pricing(3e-6, 15e-6, 3.75e-6, 0.3e-6, True))
        add("claude-sonnet-4", Pricing(3e-6, 15e-6, 3.75e-6, 0.3e-6, True,
                                       input_above_200k=6e-6,
                                       output_above_200k=22.5e-6,
                                       cache_create_above_200k=7.5e-6,
                                       cache_read_above_200k=0.6e-6))

        claude_3_5_haiku = Pricing(0.8e-6, 4e-6, 1.0e-6, 0.08e-6, True)
        add("claude-3-5-haiku", claude_3_5_haiku)
        add("claude-3-5-haiku-20241022", claude_3_5_haiku)

        add("claude-3-opus", Pricing(15e-6, 75e-6, 18.75e-6, 1.5e-6, True))
        add("claude-3-sonnet", Pricing(3e-6, 15e-6, 3.75e-6, 0.3e-6, True))
        add("claude-3-haiku", Pricing(0.25e-6, 1.25e-6, 0.3e-6, 0.03e-6, True))

        add("gpt-5", Pricing(1.25e-6, 10e-6, 1.25e-6, 0.125e-6, True))
        add("gpt-5.5", Pricing(5e-6, 30e-6, 5e-6, 0.5e-6, True,
                               fast_multiplier=fast_multiplier_overrides.multiplier_for("gpt-5.5") or 1.0))
        add("grok-4.3", Pricing(1.25e-6, 2.5e-6, 1.25e-6, 0.125e-6, False))

        add("moonshot/kimi-k2.5", Pricing(0.6e-6, 3e-6, 0.75e-6, 0.1e-6, True))
        add("moonshot/kimi-k2.6", Pricing(0.95e-6, 4e-6, 1.1875e-6, 0.16e-6, True))

        gpt_5_1_pricing = Pricing(1.25e-6, 10e-6, 1.25e-6, 0.125e-6, True)
        add("gpt-5.1", gpt_5_1_pricing)
        add("gpt-5.1-codex", gpt_5_1_pricing)

        gpt_5_codex_pricing = Pricing(1.75e-6, 14e-6, 1.75e-6, 0.175e-6, True)
        add("gpt-5.2-codex", gpt_5_codex_pricing)
        add("gpt-5.3-codex", Pricing(1.75e-6, 14e-6, 1.75e-6, 0.175e-6, True,
                                     fast_multiplier=fast_multiplier_overrides.multiplier_for("gpt-5.3-codex") or 1.0))
        add("gpt-5.2", gpt_5_codex_pricing)
        add("gpt-5.4", Pricing(2.5e-6, 15e-6, 2.5e-6, 0.25e-6, True,
                               fast_multiplier=fast_multiplier_overrides.multiplier_for("gpt-5.4") or 1.0))
        add("gpt-5.4-mini", Pricing(0.75e-6, 4.5e-6, 0.75e-6, 0.075e-6, True))
        add("gpt-5.4-nano", Pricing(0.2e-6, 1.25e-6, 0.2e-6, 0.02e-6, True))

        def glm_pricing(inp, out, cache_read):
            return Pricing(inp, out, 0.0, cache_read, True)

        glm_base = glm_pricing(0.6e-6, 2.2e-6, 0.11e-6)
        add("glm-4.5", glm_base)
        add("zai/glm-4.5", glm_base)
        add("zai/glm-4.5-x", glm_pricing(2.2e-6, 8.9e-6, 0.45e-6))
        add("zai/glm-4.5-air", glm_pricing(0.2e-6, 1.1e-6, 0.03e-6))
        add("zai/glm-4.5-airx", glm_pricing(1.1e-6, 4.5e-6, 0.22e-6))
        add("zai/glm-4.5v", glm_pricing(0.6e-6, 1.8e-6, 0.11e-6))
        add("zai/glm-4-32b-0414-128k", glm_pricing(0.1e-6, 0.1e-6, 0.0))
        add("zai/glm-4.5-flash", glm_pricing(0.0, 0.0, 0.0))
        add("glm-4.6", glm_base)
        add("glm-4.7", glm_base)
        add("glm-5", Pricing(1.0e-6, 3.2e-6, 0.0, 0.2e-6, True))
        add("glm-5-turbo", Pricing(1.2e-6, 4.0e-6, 0.0, 0.24e-6, True))
        add("glm-5.1", Pricing(1.4e-6, 4.4e-6, 0.0, 0.26e-6, True))

        self.context_limits["gpt-5.5"] = 1050000
        self.context_limits["grok-4.3"] = 1000000
        self.context_limits["gpt-5.4"] = 1050000
        for model in ["claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6"]:
            self.context_limits[model] = 1000000
        self.context_limits["moonshot/kimi-k2.5"] = 262144
        self.context_limits["moonshot/kimi-k2.6"] = 262144
        for model in ["claude-opus-4-5", "claude-haiku-4-5", "claude-opus-4", "claude-sonnet-4",
                      "claude-3-5-haiku", "claude-3-5-haiku-20241022", "claude-3-opus", "claude-3-sonnet",
                      "claude-3-haiku"]:
            self.context_limits[model] = 200000

    def len(self):
        return len(self.entries)


# Lazy caches for fallbacks
_embedded_models_dev_pricing: Optional[PricingMap] = None
_models_dev_pricing_cache: Optional[PricingMap] = None


def get_embedded_models_dev_pricing() -> PricingMap:
    global _embedded_models_dev_pricing
    if _embedded_models_dev_pricing is None:
        _embedded_models_dev_pricing = PricingMap()
        _embedded_models_dev_pricing.load_models_dev_json_missing(MODELS_DEV_PRICING)
    return _embedded_models_dev_pricing


def get_models_dev_pricing_cache() -> Optional[PricingMap]:
    global _models_dev_pricing_cache
    if _models_dev_pricing_cache is None:
        # In Python, we can just use the embedded models.dev pricing as a mock fallback
        # or load dynamically if needed. For tests and porting, using the embedded snapshot is perfect.
        _models_dev_pricing_cache = get_embedded_models_dev_pricing()
    return _models_dev_pricing_cache


# Cost calculations
class CacheCreationRaw:
    def __init__(self, ephemeral_5m_input_tokens: int = 0, ephemeral_1h_input_tokens: int = 0):
        self.ephemeral_5m_input_tokens = ephemeral_5m_input_tokens
        self.ephemeral_1h_input_tokens = ephemeral_1h_input_tokens


class TokenUsageRaw:
    def __init__(self,
                 input_tokens: int = 0,
                 output_tokens: int = 0,
                 cache_creation_input_tokens: int = 0,
                 cache_read_input_tokens: int = 0,
                 speed: Optional[str] = None,  # "fast" or "standard"
                 cache_creation: Optional[CacheCreationRaw] = None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.speed = speed
        self.cache_creation = cache_creation

    def cache_creation_token_count(self) -> int:
        if self.cache_creation:
            return self.cache_creation.ephemeral_5m_input_tokens + self.cache_creation.ephemeral_1h_input_tokens
        return self.cache_creation_input_tokens


def tiered_cost(tokens: int, base: float, above: Optional[float]) -> float:
    threshold = 200000
    if tokens == 0:
        return 0.0
    if above is not None and tokens > threshold:
        return (threshold * base) + ((tokens - threshold) * above)
    return tokens * base


def calculate_cost_from_tokens(
    model: Optional[str],
    usage: TokenUsageRaw,
    pricing_map: Optional[PricingMap]
) -> float:
    if model is None:
        return 0.0
    if pricing_map is None:
        return 0.0
    pricing = pricing_map.find(model)
    if pricing is None:
        return 0.0

    multiplier = pricing.fast_multiplier if usage.speed == "fast" else 1.0

    if usage.cache_creation is not None:
        cache_create_5m_tokens = usage.cache_creation.ephemeral_5m_input_tokens
        cache_create_1h_tokens = usage.cache_creation.ephemeral_1h_input_tokens
    else:
        cache_create_5m_tokens = usage.cache_creation_input_tokens
        cache_create_1h_tokens = 0

    cache_create_1h_cost = pricing.input * CACHE_CREATE_1H_INPUT_MULTIPLIER
    cache_create_1h_cost_above_200k = (
        pricing.input_above_200k * CACHE_CREATE_1H_INPUT_MULTIPLIER
        if pricing.input_above_200k is not None
        else None
    )

    cost = (
        tiered_cost(usage.input_tokens, pricing.input, pricing.input_above_200k)
        + tiered_cost(usage.output_tokens, pricing.output, pricing.output_above_200k)
        + tiered_cost(cache_create_5m_tokens, pricing.cache_create, pricing.cache_create_above_200k)
        + tiered_cost(cache_create_1h_tokens, cache_create_1h_cost, cache_create_1h_cost_above_200k)
        + tiered_cost(usage.cache_read_input_tokens, pricing.cache_read, pricing.cache_read_above_200k)
    )

    return cost * multiplier


def calculate_cost_for_usage(
    model: Optional[str],
    usage: TokenUsageRaw,
    cost_usd: Optional[float],
    mode: str,  # "display", "auto", "calculate"
    pricing_map: Optional[PricingMap]
) -> float:
    if mode == "display":
        return cost_usd if cost_usd is not None else 0.0
    elif mode == "auto":
        if cost_usd is not None:
            return cost_usd
        return calculate_cost_from_tokens(model, usage, pricing_map)
    elif mode == "calculate":
        return calculate_cost_from_tokens(model, usage, pricing_map)
    return 0.0


def parse_iso_timestamp(ts_str: str):
    if ts_str.endswith('Z'):
        ts_str = ts_str[:-1] + '+00:00'
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts_str)
    except ValueError:
        return None


def is_valid_usage_entry(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    message = data.get("message")
    if not isinstance(message, dict):
        return False
        
    if "usage" not in message or not isinstance(message["usage"], dict):
        return False
    
    if "version" in data and (data["version"] is None or data["version"] == ""):
        return False
    if "sessionId" in data and (data["sessionId"] is None or data["sessionId"] == ""):
        return False
    if "requestId" in data and (data["requestId"] is None or data["requestId"] == ""):
        return False
    if "id" in message and (message["id"] is None or message["id"] == ""):
        return False
    if "model" in message and (message["model"] is None or message["model"] == ""):
        return False
    return True


def has_unsupported_null_field(line_str: str) -> bool:
    unsupported_keys = [
        "id", "cwd", "model", "speed", "costUSD", "version",
        "sessionId", "requestId", "isApiErrorMessage",
        "cache_read_input_tokens", "cache_creation_input_tokens"
    ]
    for key in unsupported_keys:
        pattern = f'"{key}"\\s*:\\s*null'
        if re.search(pattern, line_str):
            return True
    return False


def _get_claude_usage_entries_for_dates(date_set: set) -> Dict[str, list]:
    pricing_map = PricingMap.load_embedded()
    
    from datetime import datetime
    # Get local timezone dynamically
    local_tz = datetime.now().astimezone().tzinfo
    
    paths = []
    # 1. Check CLAUDE_CONFIG_DIR
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir:
        for p in env_dir.split(','):
            p = p.strip()
            if p.startswith("~"):
                home = os.path.expanduser("~")
                p = os.path.join(home, p[2:]) if p.startswith("~/") else home
            if os.path.isdir(os.path.join(p, "projects")):
                paths.append(p)
                
    # 2. Check XDG_CONFIG_HOME & default home path
    if not paths:
        home = os.path.expanduser("~")
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            p = os.path.join(xdg_config, "claude")
        else:
            p = os.path.join(home, ".config", "claude")
        if os.path.isdir(os.path.join(p, "projects")):
            paths.append(p)
            
        p_home = os.path.join(home, ".claude")
        if os.path.isdir(os.path.join(p_home, "projects")) and p_home not in paths:
            paths.append(p_home)
            
    if not paths:
        return {d: [] for d in date_set}
        
    jsonl_files = []
    for base_path in paths:
        projects_path = os.path.join(base_path, "projects")
        for root, _, files in os.walk(projects_path):
            for file in files:
                if file.endswith(".jsonl"):
                    jsonl_files.append(os.path.join(root, file))
                    
    entries_by_date = {d: [] for d in date_set}
    for file_path in jsonl_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"usage":{' not in line:
                        continue
                    if has_unsupported_null_field(line):
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                        
                    if not is_valid_usage_entry(data):
                        continue
                        
                    ts_str = data.get("timestamp")
                    if not ts_str:
                        continue
                        
                    dt_utc = parse_iso_timestamp(ts_str)
                    if not dt_utc:
                        continue
                        
                    dt_local = dt_utc.astimezone(local_tz)
                    day_str = dt_local.strftime("%Y-%m-%d")
                    if day_str not in date_set:
                        continue
                        
                    entries_by_date[day_str].append((dt_local, data))
        except Exception:
            pass
            
    result = {}
    for day_str in date_set:
        entries = entries_by_date[day_str]
        loaded_entries = []
        for dt, data in entries:
            message = data["message"]
            usage_raw = message["usage"]
            
            cache_creation_raw = None
            if "cache_creation" in usage_raw and isinstance(usage_raw["cache_creation"], dict):
                cc = usage_raw["cache_creation"]
                cache_creation_raw = CacheCreationRaw(
                    ephemeral_5m_input_tokens=cc.get("ephemeral5mInputTokens") or cc.get("ephemeral_5m_input_tokens") or 0,
                    ephemeral_1h_input_tokens=cc.get("ephemeral1hInputTokens") or cc.get("ephemeral_1h_input_tokens") or 0
                )
                
            usage = TokenUsageRaw(
                input_tokens=usage_raw.get("inputTokens") or usage_raw.get("input_tokens") or 0,
                output_tokens=usage_raw.get("outputTokens") or usage_raw.get("output_tokens") or 0,
                cache_creation_input_tokens=usage_raw.get("cacheCreationInputTokens") or usage_raw.get("cache_creation_input_tokens") or 0,
                cache_read_input_tokens=usage_raw.get("cacheReadInputTokens") or usage_raw.get("cache_read_input_tokens") or 0,
                speed=usage_raw.get("speed"),
                cache_creation=cache_creation_raw
            )
            
            raw_model = message.get("model")
            model_name = raw_model
            if model_name and model_name != "<synthetic>":
                if usage.speed == "fast":
                    model_name = f"{model_name}-fast"
                    
            cost = calculate_cost_from_tokens(model_name, usage, pricing_map)
            loaded_entries.append({
                "data": data,
                "usage": usage,
                "model_name": model_name,
                "cost": cost
            })
            
        deduped_list = []
        msg_to_indices = {}
        for entry in loaded_entries:
            message_id = entry["data"]["message"].get("id")
            request_id = entry["data"].get("requestId")
            is_sidechain = entry["data"].get("isSidechain") == True
            
            found_idx = None
            if message_id:
                if message_id in msg_to_indices:
                    for idx in msg_to_indices[message_id]:
                        existing = deduped_list[idx]
                        if existing["data"].get("requestId") == request_id:
                            found_idx = idx
                            break
                    if found_idx is None:
                        for idx in msg_to_indices[message_id]:
                            existing = deduped_list[idx]
                            existing_sidechain = existing["data"].get("isSidechain") == True
                            if is_sidechain or existing_sidechain:
                                found_idx = idx
                                break
                                
            if found_idx is not None:
                existing = deduped_list[found_idx]
                cand_is_sidechain = is_sidechain
                exist_is_sidechain = existing["data"].get("isSidechain") == True
                
                replace = False
                if cand_is_sidechain != exist_is_sidechain:
                    replace = exist_is_sidechain
                else:
                    cand_total = (entry["usage"].input_tokens + entry["usage"].output_tokens + 
                                  entry["usage"].cache_creation_token_count() + entry["usage"].cache_read_input_tokens)
                    exist_total = (existing["usage"].input_tokens + existing["usage"].output_tokens + 
                                   existing["usage"].cache_creation_token_count() + existing["usage"].cache_read_input_tokens)
                    if cand_total != exist_total:
                        replace = cand_total > exist_total
                    else:
                        replace = entry["usage"].speed is not None and existing["usage"].speed is None
                if replace:
                    deduped_list[found_idx] = entry
            else:
                new_idx = len(deduped_list)
                deduped_list.append(entry)
                if message_id:
                    if message_id not in msg_to_indices:
                        msg_to_indices[message_id] = []
                    msg_to_indices[message_id].append(new_idx)
                    
        result[day_str] = deduped_list
        
    return result


def _get_claude_usage_entries(date_str: str) -> list:
    res = _get_claude_usage_entries_for_dates({date_str})
    return res.get(date_str, [])


# --- Codex / ChatGPT Parser & Helpers ---

def codex_paths() -> List[Dict[str, str]]:
    env_paths = os.environ.get("CODEX_HOME")
    if env_paths:
        homes = [p.strip() for p in env_paths.split(',') if p.strip()]
    else:
        homes = [os.path.expanduser("~/.codex")]
        
    sources = []
    seen_dirs = set()
    for home in homes:
        home = os.path.abspath(home)
        sessions = os.path.join(home, "sessions")
        archived_sessions = os.path.join(home, "archived_sessions")
        found_usage_dir = False
        if os.path.isdir(sessions):
            if sessions not in seen_dirs:
                seen_dirs.add(sessions)
                sources.append({"dir": sessions, "dedupe_scope": home})
            found_usage_dir = True
        if os.path.isdir(archived_sessions):
            if archived_sessions not in seen_dirs:
                seen_dirs.add(archived_sessions)
                sources.append({"dir": archived_sessions, "dedupe_scope": home})
            found_usage_dir = True
        if not found_usage_dir:
            if home not in seen_dirs:
                seen_dirs.add(home)
                sources.append({"dir": home, "dedupe_scope": home})
    return sources


def collect_deduped_codex_files(sources: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    seen_files = set()
    groups = []
    for source in sources:
        source_dir = source["dir"]
        dedupe_scope = source["dedupe_scope"]
        files_in_dir = []
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.endswith(".jsonl"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, source_dir)
                    rel_path_key = rel_path.replace("\\", "/")
                    key = (dedupe_scope, rel_path_key)
                    if key not in seen_files:
                        seen_files.add(key)
                        files_in_dir.append(full_path)
        if files_in_dir:
            files_in_dir.sort()
            groups.append({
                "dir": source_dir,
                "files": files_in_dir
            })
    return groups


def codex_session_id(sessions_dir: str, file_path: str) -> str:
    rel = os.path.relpath(file_path, sessions_dir)
    name, _ = os.path.splitext(rel)
    session_id = name.replace("\\", "/")
    if not session_id:
        session_id = "unknown"
    return session_id


def is_codex_subagent_session(file_path: str) -> bool:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(16 * 1024)
            return "thread_spawn" in content
    except Exception:
        return False


def detect_subagent_replay_second(file_path: str) -> Optional[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_second = None
            for line in f:
                if '"type":"event_msg"' not in line:
                    continue
                if '"type":"token_count"' not in line:
                    continue
                try:
                    value = json.loads(line)
                except Exception:
                    continue
                if value.get("type") != "event_msg":
                    continue
                payload = value.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "token_count":
                    continue
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue
                if "last_token_usage" not in info and "total_token_usage" not in info:
                    continue
                ts = value.get("timestamp")
                if not ts:
                    continue
                normalized_ts = normalize_timestamp(ts)
                if not normalized_ts or len(normalized_ts) < 19:
                    continue
                ts_second = normalized_ts[:19]
                if first_second is None:
                    first_second = ts_second
                else:
                    if first_second == ts_second:
                        return ts_second
                    return None
    except Exception:
        pass
    return None


def normalize_timestamp(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        if codex_timestamp_date(val):
            return val
        dt = parse_iso_timestamp(val)
        if dt:
            return format_rfc3339_millis(dt)
        return None
    if isinstance(val, (int, float)):
        raw = int(val)
        millis = raw if raw > 10_000_000_000 else raw * 1000
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
        return format_rfc3339_millis(dt)
    return None


def codex_timestamp_date(timestamp: str) -> Optional[str]:
    if len(timestamp) < 10:
        return None
    date_part = timestamp[:10]
    if (len(date_part) == 10 and 
        date_part[0:4].isdigit() and 
        date_part[4] == '-' and 
        date_part[5:7].isdigit() and 
        date_part[7] == '-' and 
        date_part[8:10].isdigit()):
        try:
            from datetime import datetime
            datetime.strptime(date_part, "%Y-%m-%d")
            return date_part
        except ValueError:
            return None
    return None


def format_rfc3339_millis(dt) -> str:
    from datetime import timezone
    dt_utc = dt.astimezone(timezone.utc)
    formatted = dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return formatted[:-3] + "Z"


def parsed_model_is_missing(model: Optional[str], current_model: Optional[str], current_model_is_fallback: bool) -> bool:
    return model is not None and current_model is not None and current_model_is_fallback


def resolve_codex_usage_model(
    parsed_model: Optional[str],
    timestamp: str,
    current_model: List[Optional[str]],
    current_model_is_fallback: List[bool],
    file_mtime: str
) -> Tuple[Optional[str], bool]:
    if parsed_model:
        current_model[0] = parsed_model
        current_model_is_fallback[0] = False
        
    is_fallback_model = False
    model = parsed_model
    if not model:
        model = current_model[0]
        
    if not model:
        is_fallback_model = True
        current_model_is_fallback[0] = True
        current_model[0] = "gpt-5"
        model = "gpt-5"
        
    if current_model_is_fallback[0]:
        is_fallback_model = True
        
    if parsed_model_is_missing(model, current_model[0], current_model_is_fallback[0]):
        is_fallback_model = True
        
    if model == "codex-auto-review":
        is_fallback_model = True
        date = codex_timestamp_date(timestamp)
        if not date:
            date = codex_timestamp_date(file_mtime)
        if not date:
            model = "gpt-5"
        else:
            model = codex_log_model_fallback(date)
            
    return model, is_fallback_model


def codex_log_model_fallback(date_str: str) -> str:
    fallbacks = [
        {"releasedOn": "2026-04-23", "model": "gpt-5.5"},
        {"releasedOn": "2026-03-05", "model": "gpt-5.4"},
        {"releasedOn": "2026-02-05", "model": "gpt-5.3-codex"},
        {"releasedOn": "2025-12-11", "model": "gpt-5.2-codex"},
        {"releasedOn": "2025-11-13", "model": "gpt-5.1-codex"},
        {"releasedOn": "2025-09-15", "model": "gpt-5-codex"},
        {"releasedOn": "2025-08-07", "model": "gpt-5"},
    ]
    for f in fallbacks:
        if date_str >= f["releasedOn"]:
            return f["model"]
    return "gpt-5"


def file_modified_timestamp(file_path: str) -> str:
    try:
        mtime = os.path.getmtime(file_path)
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return format_rfc3339_millis(dt)
    except Exception:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(0, tz=timezone.utc)
        return format_rfc3339_millis(dt)


def deserialize_codex_raw_usage(val: Any) -> Optional[Dict[str, int]]:
    if not isinstance(val, dict):
        return None
    input_tokens = get_lossy_u64(val, "input_tokens")
    prompt_tokens = get_lossy_u64(val, "prompt_tokens")
    inp_val = get_lossy_u64(val, "input")
    
    cached_input_tokens = get_lossy_u64(val, "cached_input_tokens")
    cache_read_input_tokens = get_lossy_u64(val, "cache_read_input_tokens")
    cached_tokens = get_lossy_u64(val, "cached_tokens")
    
    output_tokens = get_lossy_u64(val, "output_tokens")
    completion_tokens = get_lossy_u64(val, "completion_tokens")
    out_val = get_lossy_u64(val, "output")
    
    reasoning_output_tokens = get_lossy_u64(val, "reasoning_output_tokens")
    reasoning_tokens = get_lossy_u64(val, "reasoning_tokens")
    
    total_tokens = get_lossy_u64(val, "total_tokens")
    
    input_count = input_tokens if input_tokens is not None else (prompt_tokens if prompt_tokens is not None else (inp_val if inp_val is not None else 0))
    output_count = output_tokens if output_tokens is not None else (completion_tokens if completion_tokens is not None else (out_val if out_val is not None else 0))
    reasoning_count = reasoning_output_tokens if reasoning_output_tokens is not None else (reasoning_tokens if reasoning_tokens is not None else 0)
    cached_count = cached_input_tokens if cached_input_tokens is not None else (cache_read_input_tokens if cache_read_input_tokens is not None else (cached_tokens if cached_tokens is not None else 0))
    
    if total_tokens is not None and (total_tokens > 0 or input_count + output_count + reasoning_count == 0):
        total_count = total_tokens
    else:
        total_count = input_count + output_count + reasoning_count
        
    return {
        "input_tokens": input_count,
        "cached_input_tokens": cached_count,
        "output_tokens": output_count,
        "reasoning_output_tokens": reasoning_count,
        "total_tokens": total_count
    }


def get_lossy_u64(d: Dict[str, Any], key: str) -> Optional[int]:
    val = d.get(key)
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val.strip())
        except ValueError:
            return None
    return None


def subtract_codex_raw_usage(current: Dict[str, int], previous: Optional[Dict[str, int]]) -> Dict[str, int]:
    prev = previous or {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 0}
    return {
        "input_tokens": max(0, current["input_tokens"] - prev["input_tokens"]),
        "cached_input_tokens": max(0, current["cached_input_tokens"] - prev["cached_input_tokens"]),
        "output_tokens": max(0, current["output_tokens"] - prev["output_tokens"]),
        "reasoning_output_tokens": max(0, current["reasoning_output_tokens"] - prev["reasoning_output_tokens"]),
        "total_tokens": max(0, current["total_tokens"] - prev["total_tokens"]),
    }


def get_non_empty_str(d: Any, keys: List[str]) -> Optional[str]:
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if isinstance(v, str):
            v = v.strip()
            if v:
                return v
    return None


def codex_model_from_payload(payload: dict) -> Optional[str]:
    m = get_non_empty_str(payload, ["model", "model_name"])
    if m:
        return m
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        return get_non_empty_str(meta, ["model"])
    return None


def codex_model_from_info(info: dict) -> Optional[str]:
    m = get_non_empty_str(info, ["model", "model_name"])
    if m:
        return m
    meta = info.get("metadata")
    if isinstance(meta, dict):
        return get_non_empty_str(meta, ["model"])
    return None


def codex_model_from_result(entry: dict) -> Optional[str]:
    m = get_non_empty_str(entry, ["model", "model_name"])
    if m:
        return m
    meta = entry.get("metadata")
    if isinstance(meta, dict):
        m = get_non_empty_str(meta, ["model"])
        if m:
            return m
            
    for key in ["data", "result", "response"]:
        sub = entry.get(key)
        if isinstance(sub, dict):
            m = get_non_empty_str(sub, ["model", "model_name"])
            if m:
                return m
            sub_meta = sub.get("metadata")
            if isinstance(sub_meta, dict):
                m = get_non_empty_str(sub_meta, ["model"])
                if m:
                    return m
    return None


def visit_codex_session_file(sessions_dir: str, file_path: str) -> List[Dict[str, Any]]:
    is_subagent = is_codex_subagent_session(file_path)
    replay_second = detect_subagent_replay_second(file_path) if is_subagent else None
    
    events = []
    session_id = codex_session_id(sessions_dir, file_path)
    previous_totals = None
    current_model = [None]
    current_model_is_fallback = [False]
    fallback_timestamp = file_modified_timestamp(file_path)
    skip_replay = replay_second is not None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                is_session = False
                is_headless = False
                
                if '"type"' in line and ('"turn_context"' in line or ('"event_msg"' in line and '"token_count"' in line)):
                    is_session = True
                elif '"usage"' in line or '"input_tokens"' in line or '"prompt_tokens"' in line:
                    is_headless = True
                    
                if not is_session and not is_headless:
                    if '"type"' in line:
                        is_session = True
                    else:
                        continue
                        
                if is_session:
                    try:
                        value = json.loads(line)
                    except Exception:
                        continue
                        
                    entry_type = value.get("type")
                    payload = value.get("payload")
                    
                    if entry_type == "turn_context":
                        if isinstance(payload, dict):
                            model = codex_model_from_payload(payload)
                            if model:
                                current_model[0] = model
                                current_model_is_fallback[0] = False
                        continue
                        
                    if entry_type != "event_msg":
                        continue
                        
                    if not isinstance(payload, dict) or payload.get("type") != "token_count":
                        continue
                        
                    timestamp = value.get("timestamp")
                    normalized_ts = normalize_timestamp(timestamp)
                    if not normalized_ts:
                        continue
                        
                    if replay_second and skip_replay:
                        if len(normalized_ts) >= 19 and normalized_ts[:19] == replay_second:
                            info = payload.get("info")
                            if isinstance(info, dict) and "total_token_usage" in info:
                                tot = deserialize_codex_raw_usage(info["total_token_usage"])
                                if tot:
                                    previous_totals = tot
                            continue
                        else:
                            skip_replay = False
                            
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue
                        
                    last_usage = deserialize_codex_raw_usage(info.get("last_token_usage"))
                    total_usage = deserialize_codex_raw_usage(info.get("total_token_usage"))
                    
                    raw_usage = last_usage
                    if not raw_usage and total_usage:
                        raw_usage = subtract_codex_raw_usage(total_usage, previous_totals)
                        
                    if total_usage:
                        previous_totals = total_usage
                        
                    if not raw_usage:
                        continue
                        
                    if (raw_usage["input_tokens"] == 0 and
                        raw_usage["cached_input_tokens"] == 0 and
                        raw_usage["output_tokens"] == 0 and
                        raw_usage["reasoning_output_tokens"] == 0):
                        continue
                        
                    parsed_model = codex_model_from_payload(payload) or codex_model_from_info(info)
                    model, is_fallback = resolve_codex_usage_model(
                        parsed_model, normalized_ts, current_model, current_model_is_fallback, fallback_timestamp
                    )
                    
                    events.append({
                        "session_id": session_id,
                        "timestamp": normalized_ts,
                        "model": model,
                        "input_tokens": raw_usage["input_tokens"],
                        "cached_input_tokens": min(raw_usage["cached_input_tokens"], raw_usage["input_tokens"]),
                        "output_tokens": raw_usage["output_tokens"],
                        "reasoning_output_tokens": raw_usage["reasoning_output_tokens"],
                        "total_tokens": raw_usage["total_tokens"],
                        "is_fallback_model": is_fallback
                    })
                    
                elif is_headless:
                    try:
                        value = json.loads(line)
                    except Exception:
                        continue
                        
                    usage_obj = value.get("usage")
                    if not usage_obj:
                        data = value.get("data")
                        if isinstance(data, dict):
                            usage_obj = data.get("usage")
                    if not usage_obj:
                        res = value.get("result")
                        if isinstance(res, dict):
                            usage_obj = res.get("usage")
                    if not usage_obj:
                        resp = value.get("response")
                        if isinstance(resp, dict):
                            usage_obj = resp.get("usage")
                            
                    raw_usage = deserialize_codex_raw_usage(usage_obj)
                    if not raw_usage:
                        continue
                        
                    if (raw_usage["input_tokens"] == 0 and
                        raw_usage["cached_input_tokens"] == 0 and
                        raw_usage["output_tokens"] == 0 and
                        raw_usage["reasoning_output_tokens"] == 0 and
                        raw_usage["total_tokens"] == 0):
                        continue
                        
                    parsed_model = codex_model_from_result(value)
                    
                    ts_val = value.get("timestamp") or value.get("created_at") or value.get("createdAt")
                    if not ts_val:
                        for key in ["data", "result", "response"]:
                            sub = value.get(key)
                            if isinstance(sub, dict):
                                ts_val = sub.get("timestamp") or sub.get("created_at") or sub.get("createdAt")
                                if ts_val:
                                    break
                                    
                    normalized_ts = normalize_timestamp(ts_val) or fallback_timestamp
                    
                    model, is_fallback = resolve_codex_usage_model(
                        parsed_model, normalized_ts, current_model, current_model_is_fallback, fallback_timestamp
                    )
                    
                    events.append({
                        "session_id": session_id,
                        "timestamp": normalized_ts,
                        "model": model,
                        "input_tokens": raw_usage["input_tokens"],
                        "cached_input_tokens": min(raw_usage["cached_input_tokens"], raw_usage["input_tokens"]),
                        "output_tokens": raw_usage["output_tokens"],
                        "reasoning_output_tokens": raw_usage["reasoning_output_tokens"],
                        "total_tokens": raw_usage["total_tokens"],
                        "is_fallback_model": is_fallback
                    })
    except Exception:
        pass
    return events


def get_codex_usage_for_dates(date_set: set) -> Dict[str, List[Dict[str, Any]]]:
    sources = codex_paths()
    groups = collect_deduped_codex_files(sources)
    
    events = []
    for group in groups:
        for file_path in group["files"]:
            events.extend(visit_codex_session_file(group["dir"], file_path))
            
    seen = set()
    deduped = []
    for e in events:
        key = (
            e["timestamp"],
            e["model"],
            e["input_tokens"],
            e["cached_input_tokens"],
            e["output_tokens"],
            e["reasoning_output_tokens"],
            e["total_tokens"]
        )
        if key not in seen:
            seen.add(key)
            deduped.append(e)
            
    from datetime import datetime
    local_tz = datetime.now().astimezone().tzinfo
    
    result = {d: [] for d in date_set}
    for e in deduped:
        dt_utc = parse_iso_timestamp(e["timestamp"])
        if not dt_utc:
            continue
        dt_local = dt_utc.astimezone(local_tz)
        day_str = dt_local.strftime("%Y-%m-%d")
        if day_str in date_set:
            result[day_str].append(e)
            
    return result


def get_codex_usage_for_date(date_str: str) -> List[Dict[str, Any]]:
    res = get_codex_usage_for_dates({date_str})
    return res.get(date_str, [])



def detect_codex_speed() -> str:
    env_paths = os.environ.get("CODEX_HOME")
    if env_paths:
        homes = [p.strip() for p in env_paths.split(',') if p.strip()]
    else:
        homes = [os.path.expanduser("~/.codex")]
        
    for home in homes:
        cfg_path = os.path.join(home, "config.toml")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        setting = line.split('#')[0].strip()
                        if '=' in setting:
                            key, val = setting.split('=', 1)
                            if key.strip() == "service_tier":
                                val = val.strip().strip('"').strip("'")
                                if val in ("fast", "priority"):
                                    return "fast"
            except Exception:
                pass
    return "standard"


def calculate_codex_model_cost(
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    pricing_map: PricingMap,
    speed: str
) -> float:
    pricing = pricing_map.find(model)
    if not pricing:
        return 0.0
        
    non_cached_input = max(0, input_tokens - cached_input_tokens)
    
    if speed == "fast":
        multiplier = pricing.fast_multiplier if pricing.fast_multiplier != 1.0 else 2.0
    else:
        multiplier = 1.0
        
    cache_read = pricing.cache_read if pricing.cache_read_explicit else pricing.input
    
    cost = (
        non_cached_input * pricing.input +
        cached_input_tokens * cache_read +
        output_tokens * pricing.output
    )
    return cost * multiplier
