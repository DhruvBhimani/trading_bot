package com.solanaquant.features;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
public class TokenSafetyEvaluator {

    public record SafetyResult(short score, List<String> flags) {
    }

    public SafetyResult evaluate(Map<String, Object> features) {
        int score = 100;
        List<String> flags = new ArrayList<>();

        if (!bool(features, "mint_authority_revoked", true)) {
            score -= 35;
            flags.add("mint_authority_active");
        }
        if (!bool(features, "freeze_authority_revoked", true)) {
            score -= 25;
            flags.add("freeze_authority_active");
        }
        if (!bool(features, "liquidity_locked", true)) {
            score -= 20;
            flags.add("liquidity_unlocked");
        }

        double top10 = number(features, "top10_holder_pct", 100);
        if (top10 > 45) {
            score -= 25;
            flags.add("high_holder_concentration");
        } else if (top10 > 30) {
            score -= 10;
            flags.add("elevated_holder_concentration");
        }

        if (bool(features, "bundled_launch", false)) {
            score -= 30;
            flags.add("bundled_launch");
        }
        if (bool(features, "deployer_sold_recently", false)) {
            score -= 20;
            flags.add("deployer_distribution");
        }

        score = Math.max(0, Math.min(100, score));
        return new SafetyResult((short) score, flags);
    }

    private static boolean bool(Map<String, Object> map, String key, boolean defaultValue) {
        Object value = map.get(key);
        if (value instanceof Boolean b) {
            return b;
        }
        if (value instanceof String s) {
            return Boolean.parseBoolean(s);
        }
        return defaultValue;
    }

    private static double number(Map<String, Object> map, String key, double defaultValue) {
        Object value = map.get(key);
        if (value instanceof Number n) {
            return n.doubleValue();
        }
        return defaultValue;
    }
}
