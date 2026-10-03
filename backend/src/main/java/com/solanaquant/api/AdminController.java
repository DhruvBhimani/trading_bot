package com.solanaquant.api;

import com.solanaquant.ingestion.SampleDatasetService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final SampleDatasetService sampleDatasetService;

    public AdminController(SampleDatasetService sampleDatasetService) {
        this.sampleDatasetService = sampleDatasetService;
    }

    @PostMapping("/load-sample-data")
    public Map<String, Object> loadSampleData() {
        return sampleDatasetService.loadSampleDataset();
    }
}
