import time
import random
import statistics
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from nsga2_scheduler import NSGA2Scheduler
from tabulate import tabulate

def generate_mock_exams(num_exams=5) -> List[Dict[str, Any]]:
    """Generates a random list of exams for testing."""
    subjects = [
        "Math", "Physics", "Chemistry", "Biology", "English", "History", "CS", "Economics",
        "Geography", "Literature", "Psychology", "Sociology", "Art", "Music"
    ]
    exams = []
    start_date = datetime.now() + timedelta(days=30)
    
    # Shuffle subjects to pick random ones
    selected_subjects = random.sample(subjects, num_exams)
    
    for i, subj in enumerate(selected_subjects):
        # Random date within a 2-week exam period
        exam_date = start_date + timedelta(days=random.randint(0, 14))
        
        exams.append({
            "subject": subj,
            "date": exam_date.strftime("%Y-%m-%d"),
            "start_time": "10:00",
            "end_time": "13:00",
            "paper": "Paper 1",
            "selected": True
        })
    
    # Sort by date
    exams.sort(key=lambda x: x["date"])
    return exams

class BenchmarkSuite:
    def __init__(self):
        self.scheduler = NSGA2Scheduler()
        self.results = {}

    def run_benchmark(self, num_runs=5, num_exams_list=[5, 10]):
        """Runs the benchmark suite with different complexities."""
        print(f"🚀 Starting Benchmark Suite ({num_runs} runs per scenario)...")
        
        for num_exams in num_exams_list:
            scenario_name = f"{num_exams}_exams"
            print(f"\nEvaluating Scenario: {scenario_name}")
            
            metrics = {
                "success_rate": 0,
                "avg_generation_time": [],
                "cramming_scores": [],
                "switching_scores": [],
                "revision_scores": [],
                "hypervolume": [],
                "soft_penalty": [],
                "compactness": [],
                "load_balance": []
            }
            
            for _ in range(num_runs):
                exams = generate_mock_exams(num_exams)
                
                start_time = time.time()
                try:
                    result = self.scheduler.generate_schedule(exams)
                    duration = time.time() - start_time
                    
                    if result and result.get('schedules'):
                        metrics["success_rate"] += 1
                        metrics["avg_generation_time"].append(duration)
                        metrics["hypervolume"].append(result['debug_info'].get('convergence_generation', 0))
                        
                        # Analyze the "Balanced" schedule (first one)
                        balanced_sol = result['schedules'][0]
                        objs = balanced_sol['objectives']
                        schedule = balanced_sol['schedule']
                        
                        metrics["cramming_scores"].append(objs['cramming'])
                        metrics["switching_scores"].append(objs['switching'])
                        metrics["revision_scores"].append(objs['revision'])
                        
                        # Calculate Quality Metrics
                        metrics["soft_penalty"].append(self.calculate_soft_penalty(schedule))
                        metrics["compactness"].append(self.calculate_compactness(schedule))
                        metrics["load_balance"].append(self.calculate_load_balance(schedule))
                        
                except Exception as e:
                    print(f"  Run failed: {e}")

            # Aggregate results
            success_count = metrics["success_rate"]
            total_runs = num_runs
            
            self.results[scenario_name] = {
                "success_rate_pct": (success_count / total_runs) * 100,
                "avg_time_sec": statistics.mean(metrics["avg_generation_time"]) if metrics["avg_generation_time"] else 0,
                "std_time_sec": statistics.stdev(metrics["avg_generation_time"]) if len(metrics["avg_generation_time"]) > 1 else 0,
                "avg_convergence_gen": statistics.mean(metrics["hypervolume"]) if metrics["hypervolume"] else 0,
                "stability_std": statistics.stdev(metrics["cramming_scores"]) if len(metrics["cramming_scores"]) > 1 else 0,
                
                # Quality Metrics
                "avg_soft_penalty": statistics.mean(metrics["soft_penalty"]) if metrics["soft_penalty"] else 0,
                "avg_compactness": statistics.mean(metrics["compactness"]) if metrics["compactness"] else 0,
                "avg_load_balance": statistics.mean(metrics["load_balance"]) if metrics["load_balance"] else 0,
                
                # Objective Metrics
                "avg_cramming": statistics.mean(metrics["cramming_scores"]) if metrics["cramming_scores"] else 0,
                "avg_switching": statistics.mean(metrics["switching_scores"]) if metrics["switching_scores"] else 0,
                "avg_revision": statistics.mean(metrics["revision_scores"]) if metrics["revision_scores"] else 0
            }
            
        self.print_report()
        return self.results

    def calculate_soft_penalty(self, schedule) -> float:
        """
        Calculates Soft Constraint Penalty (P_soft).
        Weights:
        - Study > 8 hours/day: Weight 10
        - Continuous study > 4 hours: Weight 5
        """
        penalty = 0
        for day in schedule:
            daily_hours = sum(s['hours'] for s in day['sessions'])
            if daily_hours > 8:
                penalty += 10 * (daily_hours - 8)
            
            # Continuous study (simple proxy: single session > 4h)
            for s in day['sessions']:
                if s['hours'] > 4:
                    penalty += 5
        return penalty

    def calculate_compactness(self, schedule) -> float:
        """
        Calculates Compactness (Fragmentation Ratio): Total number of independent study blocks.
        Lower is better (less fragmented).
        """
        gaps = 0
        for day in schedule:
            if len(day['sessions']) > 1:
                gaps += len(day['sessions']) - 1
        return gaps

    def calculate_load_balance(self, schedule) -> float:
        """
        Calculates Load Balancing: Standard Deviation of daily study hours.
        """
        daily_hours = [sum(s['hours'] for s in day['sessions']) for day in schedule]
        if not daily_hours: return 0
        return statistics.stdev(daily_hours) if len(daily_hours) > 1 else 0

    def print_report(self):
        """Prints a summary table of the benchmark results."""
        print("\n\n📊 Benchmark Report")
        print("=" * 120)
        
        table_data = []
        for scenario, data in self.results.items():
            table_data.append([
                scenario,
                f"{data['success_rate_pct']:.0f}%",
                f"{data['avg_time_sec']:.2f}s",
                f"{data['avg_convergence_gen']:.0f}",
                f"{data['stability_std']:.2f}",
                f"{data['avg_soft_penalty']:.1f}",
                f"{data['avg_compactness']:.1f}",
                f"{data['avg_load_balance']:.2f}"
            ])
            
        headers = ["Scenario", "Success", "Time", "Conv. Gen", "Stability", "P_soft", "Compact", "Load Bal"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Save to file
        with open("benchmark_results.json", "w") as f:
            json.dump(self.results, f, indent=2)
        print("\n📝 Detailed results saved to benchmark_results.json")

if __name__ == "__main__":
    suite = BenchmarkSuite()
    # Lightweight run for verification
    suite.run_benchmark(num_runs=2, num_exams_list=[5])
