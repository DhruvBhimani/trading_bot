package com.solanaquant.strategy;

import java.util.List;
import java.util.Map;

public record SignalDecision(
        String action,
        short score,
        Map<String, Object> breakdown,
        List<String> reasons
) {
    public static SignalDecision block(short score, List<String> reasons, Map<String, Object> breakdown) {
        return new SignalDecision("BLOCK", score, breakdown, reasons);
    }

    public static SignalDecision skip(short score, List<String> reasons, Map<String, Object> breakdown) {
        return new SignalDecision("SKIP", score, breakdown, reasons);
    }

    public static SignalDecision watch(short score, List<String> reasons, Map<String, Object> breakdown) {
        return new SignalDecision("WATCH", score, breakdown, reasons);
    }

    public static SignalDecision buy(short score, List<String> reasons, Map<String, Object> breakdown) {
        return new SignalDecision("BUY", score, breakdown, reasons);
    }
}
