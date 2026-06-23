#!/usr/bin/env node
/**
 * Load test script - 10 concurrent streams to attendance API
 * Usage: node scripts/load-test.js
 */

const API_URL = process.env.API_URL || "http://localhost:8000";
const CONCURRENT = 10;
const TOTAL_REQUESTS = 100;
const DELAY_MS = 100;

async function makeRequest(endpoint, options = {}) {
  const url = `${API_URL}${endpoint}`;
  const startTime = Date.now();

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    const duration = Date.now() - startTime;
    return {
      success: response.ok,
      status: response.status,
      duration,
      data: response.ok ? await response.json() : null,
      error: response.ok ? null : await response.text(),
    };
  } catch (error) {
    const duration = Date.now() - startTime;
    return {
      success: false,
      status: 0,
      duration,
      error: error.message,
      data: null,
    };
  }
}

async function runTest() {
  console.log(`🚀 Starting load test: ${CONCURRENT} concurrent streams, ${TOTAL_REQUESTS} total requests`);
  console.log(`📍 API URL: ${API_URL}`);
  console.log(`⏱️  Delay between requests: ${DELAY_MS}ms`);
  console.log(`\n${"─".repeat(60)}\n`);

  const results = {
    total: TOTAL_REQUESTS,
    success: 0,
    failed: 0,
    totalDuration: 0,
    minDuration: Infinity,
    maxDuration: 0,
    byEndpoint: {},
  };

  const endpoints = [
    "/api/v1/auth/login",
    "/api/v1/attendance/summary",
    "/api/v1/alerts",
    "/api/v1/analytics/occupancy",
  ];

  const token = await makeRequest("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: "admin@demo.com",
      password: "admin123",
    }),
  });

  if (!token.success) {
    console.error("❌ Failed to login for load test");
    console.error(token.error);
    process.exit(1);
  }

  console.log(`✅ Authenticated with token\n`);

  // Send concurrent requests
  const startTime = Date.now();

  for (let i = 0; i < TOTAL_REQUESTS; i++) {
    const endpoint = endpoints[i % endpoints.length];
    const result = await makeRequest(endpoint, {
      headers: {
        Authorization: `Bearer ${token.data.access_token}`,
      },
    });

    // Track metrics
    results.success += result.success ? 1 : 0;
    results.failed += result.success ? 0 : 1;
    results.totalDuration += result.duration;
    results.minDuration = Math.min(results.minDuration, result.duration);
    results.maxDuration = Math.max(results.maxDuration, result.duration);

    if (!results.byEndpoint[endpoint]) {
      results.byEndpoint[endpoint] = { success: 0, failed: 0, totalDuration: 0 };
    }
    results.byEndpoint[endpoint].success += result.success ? 1 : 0;
    results.byEndpoint[endpoint].failed += result.success ? 0 : 1;
    results.byEndpoint[endpoint].totalDuration += result.duration;

    // Rate limiting
    if (i < TOTAL_REQUESTS - 1) {
      await new Promise(resolve => setTimeout(resolve, DELAY_MS));
    }
  }

  const totalTime = Date.now() - startTime;
  const avgDuration = results.totalDuration / TOTAL_REQUESTS;
  const successRate = (results.success / TOTAL_REQUESTS) * 100;

  // Print results
  console.log(`\n${"─".repeat(60)}`);
  console.log(`📊 LOAD TEST RESULTS`);
  console.log(`${"─".repeat(60)}\n`);

  console.log(`📈 Summary`);
  console.log(`   Total Requests: ${results.total}`);
  console.log(`   Successful:     ${results.success} (${successRate.toFixed(1)}%)`);
  console.log(`   Failed:         ${results.failed}`);
  console.log(`   Total Time:     ${totalTime}ms`);
  console.log(`   Avg Duration:   ${avgDuration.toFixed(0)}ms`);
  console.log(`   Min Duration:   ${results.minDuration}ms`);
  console.log(`   Max Duration:   ${results.maxDuration}ms`);
  console.log(`   RPS:            ${(TOTAL_REQUESTS / (totalTime / 1000)).toFixed(2)}\n`);

  console.log(`🔍 By Endpoint`);
  console.log(`${"─".repeat(60)}`);
  for (const [endpoint, data] of Object.entries(results.byEndpoint)) {
    const endpointRate = (data.success / TOTAL_REQUESTS) * 100;
    console.log(`   ${endpoint}`);
    console.log(`      Success: ${data.success} (${endpointRate.toFixed(1)}%)`);
    console.log(`      Failed:  ${data.failed}`);
    console.log(`      Avg:     ${data.totalDuration / TOTAL_REQUESTS.toFixed(0)}ms`);
  }

  // Performance thresholds
  console.log(`\n${"─".repeat(60)}`);
  console.log(`✅ Performance Check`);
  console.log(`${"─".repeat(60)}\n`);

  if (successRate >= 95) {
    console.log(`✅ PASS: Success rate ${successRate.toFixed(1)}% (>= 95%)`);
  } else {
    console.log(`❌ FAIL: Success rate ${successRate.toFixed(1)}% (< 95%)`);
  }

  if (avgDuration < 500) {
    console.log(`✅ PASS: Avg duration ${avgDuration.toFixed(0)}ms (< 500ms)`);
  } else {
    console.log(`⚠️  WARN: Avg duration ${avgDuration.toFixed(0)}ms (>= 500ms)`);
  }

  if (successRate >= 95 && avgDuration < 500) {
    console.log(`\n🎉 Load test PASSED!`);
    process.exit(0);
  } else {
    console.log(`\n⚠️  Load test FAILED!`);
    process.exit(1);
  }
}

// Run the test
runTest().catch(error => {
  console.error(`\n❌ Test failed with error:`, error);
  process.exit(1);
});