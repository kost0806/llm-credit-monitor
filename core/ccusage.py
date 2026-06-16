import os
from typing import Dict, Any, Optional, Set

from ccusage_pricing import (
    _get_claude_usage_entries,
    _get_claude_usage_entries_for_dates,
    resolve_model_name,
    PricingMap,
    get_codex_usage_for_date,
    get_codex_usage_for_dates,
    detect_codex_speed,
    calculate_codex_model_cost
)

def credit_usage(agent_name: str, date_str: str) -> float:
    """
    Calculates the total credit usage (USD cost) for the specified agent and date.
    
    Supported agent names:
    - 'claude': Claude Code (local log path: ~/.claude/projects)
    - 'chatgpt' or 'codex': Codex/ChatGPT (local log path: ~/.codex/sessions)
    
    Parameters:
    - agent_name (str): The name of the agent ('claude', 'chatgpt', 'codex')
    - date_str (str): The date to query (format: 'YYYY-MM-DD')
    
    Returns:
    - float: The total usage cost for the day in USD
    
    Usage Example:
    >>> from ccusage import credit_usage
    >>> cost = credit_usage('claude', '2026-06-15')
    >>> print(f"Cost: ${cost:.6f}")
    """
    agent_lower = agent_name.lower()
    if agent_lower == "claude":
        entries = _get_claude_usage_entries(date_str)
        return sum(entry["cost"] for entry in entries)
    elif agent_lower in ("chatgpt", "codex"):
        breakdown = credit_usage_per_model(agent_name, date_str)
        return sum(info["cost"] for info in breakdown.values())
    else:
        raise ValueError(f"Agent '{agent_name}' is not supported yet or has no local log paths configured.")


def credit_usage_per_model(agent_name: str, date_str: str) -> Dict[str, Dict[str, Any]]:
    """
    Returns detailed usage statistics and costs grouped by model for the specified agent and date.
    
    Supported agent names:
    - 'claude': Claude Code (local log path: ~/.claude/projects)
    - 'chatgpt' or 'codex': Codex/ChatGPT (local log path: ~/.codex/sessions)
    
    Parameters:
    - agent_name (str): The name of the agent ('claude', 'chatgpt', 'codex')
    - date_str (str): The date to query (format: 'YYYY-MM-DD')
    
    Returns:
    - Dict[str, Dict[str, Any]]: A dictionary mapping model names to their respective token counts and cost.
      
      Structure:
      {
          "model_name": {
              "input_tokens": int,           # Non-cached input tokens processed
              "output_tokens": int,          # Output tokens generated
              "cache_creation_tokens": int,  # Cache creation input tokens (Claude only, 0 for ChatGPT)
              "cache_read_tokens": int,      # Cache read input tokens
              "cost": float                  # Total cost in USD for this model
          }
      }
      
    Usage Example:
    >>> from ccusage import credit_usage_per_model
    >>> breakdown = credit_usage_per_model('chatgpt', '2026-05-07')
    >>> for model, info in breakdown.items():
    ...     print(f"Model: {model}")
    ...     print(f"  - Input Tokens: {info['input_tokens']}")
    ...     print(f"  - Output Tokens: {info['output_tokens']}")
    ...     print(f"  - Cost: ${info['cost']:.6f}")
    """
    return credit_usage_per_model_for_dates(agent_name, {date_str})[date_str]


def credit_usage_per_model_for_dates(agent_name: str, date_set: Set[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Returns detailed usage statistics and costs grouped by model for the specified agent and set of dates.
    Queries the logs only once to optimize performance.
    
    Parameters:
    - agent_name (str): The name of the agent ('claude', 'chatgpt', 'codex')
    - date_set (Set[str]): A set of date strings to query (format: 'YYYY-MM-DD')
    
    Returns:
    - Dict[str, Dict[str, Dict[str, Any]]]: A dictionary mapping each date string to its model breakdowns.
    """
    agent_lower = agent_name.lower()
    pricing_map = PricingMap.load_embedded()
    
    result = {d: {} for d in date_set}
    
    if agent_lower == "claude":
        entries_by_date = _get_claude_usage_entries_for_dates(date_set)
        for date_str, entries in entries_by_date.items():
            breakdown = result[date_str]
            for entry in entries:
                model = entry["model_name"]
                usage = entry["usage"]
                cost = entry["cost"]
                
                resolved = resolve_model_name(model)
                
                if resolved not in breakdown:
                    breakdown[resolved] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_tokens": 0,
                        "cache_read_tokens": 0,
                        "cost": 0.0
                    }
                    
                breakdown[resolved]["input_tokens"] += usage.input_tokens
                breakdown[resolved]["output_tokens"] += usage.output_tokens
                breakdown[resolved]["cache_creation_tokens"] += usage.cache_creation_token_count()
                breakdown[resolved]["cache_read_tokens"] += usage.cache_read_input_tokens
                breakdown[resolved]["cost"] += cost
                
    elif agent_lower in ("chatgpt", "codex"):
        events_by_date = get_codex_usage_for_dates(date_set)
        speed = detect_codex_speed()
        
        for date_str, events in events_by_date.items():
            breakdown = result[date_str]
            for event in events:
                model = event["model"] or "gpt-5"
                resolved = resolve_model_name(model)
                
                cost = calculate_codex_model_cost(
                    model,
                    event["input_tokens"],
                    event["cached_input_tokens"],
                    event["output_tokens"],
                    pricing_map,
                    speed
                )
                
                if resolved not in breakdown:
                    breakdown[resolved] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_tokens": 0,
                        "cache_read_tokens": 0,
                        "cost": 0.0
                    }
                    
                non_cached = max(0, event["input_tokens"] - event["cached_input_tokens"])
                
                breakdown[resolved]["input_tokens"] += non_cached
                breakdown[resolved]["output_tokens"] += event["output_tokens"]
                breakdown[resolved]["cache_creation_tokens"] += 0
                breakdown[resolved]["cache_read_tokens"] += event["cached_input_tokens"]
                breakdown[resolved]["cost"] += cost
                
    else:
        raise ValueError(f"Agent '{agent_name}' is not supported yet or has no local log paths configured.")
        
    return result


def credit_usage_last_n_days(agent_name: str, days: int, end_date_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves the credit usage and model breakdown for the last N days up to the specified end date.
    
    Parameters:
    - agent_name (str): The name of the agent ('claude', 'chatgpt', 'codex')
    - days (int): The number of days to retrieve
    - end_date_str (str, optional): The end date of the window (format: 'YYYY-MM-DD'). 
                                    Defaults to today's date in local timezone if omitted.
                                    
    Returns:
    - Dict[str, Dict[str, Any]]: A dictionary mapping each date string ('YYYY-MM-DD') to its total cost and model breakdown.
      
      Structure:
      {
          "YYYY-MM-DD": {
              "total_cost": float,
              "breakdown": {
                  "model_name": {
                      "input_tokens": int,
                      "output_tokens": int,
                      "cache_creation_tokens": int,
                      "cache_read_tokens": int,
                      "cost": float
                  }
              }
          }
      }
    """
    from datetime import datetime, timedelta
    
    if not end_date_str:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
        
    date_list = []
    for i in range(days):
        current_date = end_date - timedelta(days=i)
        day_str = current_date.strftime("%Y-%m-%d")
        date_list.append(day_str)
        
    date_set = set(date_list)
    breakdowns_by_date = credit_usage_per_model_for_dates(agent_name, date_set)
    
    result = {}
    for day_str in date_list:
        breakdown = breakdowns_by_date[day_str]
        total_cost = sum(m["cost"] for m in breakdown.values())
        result[day_str] = {
            "total_cost": total_cost,
            "breakdown": breakdown
        }
        
    return result


def credit_usage_last_30_days(agent_name: str, end_date_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves the credit usage and model breakdown for the last 30 days up to the specified end date.
    
    Parameters:
    - agent_name (str): The name of the agent ('claude', 'chatgpt', 'codex')
    - end_date_str (str, optional): The end date of the 30-day window (format: 'YYYY-MM-DD'). 
                                    Defaults to today's date in local timezone if omitted.
                                    
    Returns:
    - Dict[str, Dict[str, Any]]: A dictionary mapping each date string ('YYYY-MM-DD') to its total cost and model breakdown.
    
    Usage Example:
    >>> from ccusage import credit_usage_last_30_days
    >>> usage_data = credit_usage_last_30_days('claude')
    >>> total_30_days = sum(day['total_cost'] for day in usage_data.values())
    >>> print(f"Total Cost (Last 30 Days): ${total_30_days:.6f}")
    """
    return credit_usage_last_n_days(agent_name, 30, end_date_str)


def credit_usage_last_62_days(agent_name: str, end_date_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves the credit usage and model breakdown for the last 62 days up to the specified end date.
    
    Parameters:
    - agent_name (str): The name of the agent ('claude', 'chatgpt', 'codex')
    - end_date_str (str, optional): The end date of the 62-day window (format: 'YYYY-MM-DD'). 
                                    Defaults to today's date in local timezone if omitted.
                                    
    Returns:
    - Dict[str, Dict[str, Any]]: A dictionary mapping each date string ('YYYY-MM-DD') to its total cost and model breakdown.
    
    Usage Example:
    >>> from ccusage import credit_usage_last_62_days
    >>> usage_data = credit_usage_last_62_days('claude')
    >>> total_62_days = sum(day['total_cost'] for day in usage_data.values())
    >>> print(f"Total Cost (Last 62 Days): ${total_62_days:.6f}")
    """
    return credit_usage_last_n_days(agent_name, 62, end_date_str)
