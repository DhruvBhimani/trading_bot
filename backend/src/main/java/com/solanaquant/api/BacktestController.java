package com.solanaquant.api;

import com.solanaquant.backtest.BacktestService;
import com.solanaquant.domain.BacktestTradeEntity;
import com.solanaquant.persistence.BacktestTradeRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/backtest")
public class BacktestController {

    private final BacktestService backtestService;
    private final BacktestTradeRepository backtestTradeRepository;

    public BacktestController(BacktestService backtestService, BacktestTradeRepository backtestTradeRepository) {
        this.backtestService = backtestService;
        this.backtestTradeRepository = backtestTradeRepository;
    }

    @PostMapping("/run")
    public Map<String, Object> run() {
        return backtestService.runDefaultBacktest();
    }

    @GetMapping("/{runId}/trades")
    public List<BacktestTradeEntity> trades(@PathVariable UUID runId) {
        return backtestTradeRepository.findByRunIdOrderByEntryTimeAsc(runId);
    }
}
