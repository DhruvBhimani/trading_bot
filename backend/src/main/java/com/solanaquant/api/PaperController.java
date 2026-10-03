package com.solanaquant.api;

import com.solanaquant.paper.PaperTradingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/paper")
public class PaperController {

    private final PaperTradingService paperTradingService;

    public PaperController(PaperTradingService paperTradingService) {
        this.paperTradingService = paperTradingService;
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        return paperTradingService.status();
    }

    @PostMapping("/tick")
    public Map<String, Object> tick() {
        return paperTradingService.runTick();
    }
}
