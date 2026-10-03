package com.solanaquant.api;

import com.solanaquant.domain.SignalEventEntity;
import com.solanaquant.persistence.SignalEventRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/signals")
public class SignalController {

    private final SignalEventRepository signalEventRepository;

    public SignalController(SignalEventRepository signalEventRepository) {
        this.signalEventRepository = signalEventRepository;
    }

    @GetMapping("/recent")
    public List<SignalEventEntity> recent() {
        return signalEventRepository.findTop100ByOrderByObservedAtDesc();
    }
}
