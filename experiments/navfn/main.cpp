#include "navigo_navfn_planner/navfn.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <vector>

// 在合成地图上运行上游原始规划算法。
// 本程序不创建 ROS 节点、网络连接或 SDK 客户端，也不发送电机指令。
int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "Usage: roamerx_offline_demo OUTPUT_DIRECTORY\n";
    return 2;
  }
  std::filesystem::create_directories(argv[1]);
  constexpr int width = 180;
  constexpr int height = 120;
  constexpr double resolution = 0.1;  // 每个栅格的边长，单位：米
  constexpr double clearance_cells = 5.0;  // 测试使用的障碍间距，不代表 M1 实测外形。
  bool all_passed = true;

  std::ofstream results(std::string(argv[1]) + "/metrics.csv");
  results << "scenario,found,points,length_m,min_clearance_m,collision_free,expected_found\n";

  for (int scenario = 0; scenario < 3; ++scenario) {
    std::vector<unsigned char> occupied(width * height, 0);
    std::vector<unsigned char> costs(width * height, 0);
    auto add_wall = [&](int x0, int y0, int x1, int y1) {
      for (int y = y0; y <= y1; ++y) {
        for (int x = x0; x <= x1; ++x) {
          occupied[y * width + x] = 1;
        }
      }
    };

    add_wall(0, 0, width - 1, 0);
    add_wall(0, height - 1, width - 1, height - 1);
    add_wall(0, 0, 0, height - 1);
    add_wall(width - 1, 0, width - 1, height - 1);
    add_wall(70, 25, 100, 80);
    if (scenario == 1) {
      add_wall(55, 78, 112, 104);  // 添加障碍，使规划路径改走另一侧。
    }
    if (scenario == 2) {
      add_wall(85, 0, 90, height - 1);  // 完全隔断起点和终点，验证无路径的情况。
    }

    std::vector<std::pair<int, int>> obstacles;
    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        if (occupied[y * width + x]) {
          obstacles.emplace_back(x, y);
        }
      }
    }

    // 构造 ROS 风格的代价：间距范围内禁止通行，范围外设置渐变代价。
    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        double distance = 1e9;
        for (auto [ox, oy] : obstacles) {
          distance = std::min(distance, std::hypot(double(x - ox), double(y - oy)));
        }
        costs[y * width + x] = distance <= clearance_cells
            ? 254
            : static_cast<unsigned char>(200 * std::exp(-(distance - clearance_cells) / 5));
      }
    }

    navigo_navfn_planner::NavFn planner(width, height);
    int start[2] = {20, 60};
    int goal[2] = {155, 60};
    planner.setCostmap(costs.data(), true, false);
    planner.setStart(start);
    planner.setGoal(goal);
    const bool potential_found = planner.calcNavFnDijkstra(true);
    const int point_count = potential_found ? planner.calcPath(width * height) : 0;
    const bool found = point_count > 0;
    bool collision_free = true;
    double length = 0;
    double min_clearance = std::numeric_limits<double>::infinity();

    const std::string prefix = std::string(argv[1]) + "/scenario_" + std::to_string(scenario);
    std::ofstream grid(prefix + "_grid.csv");
    grid << "x,y,occupied,cost\n";
    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        grid << x << ',' << y << ',' << int(occupied[y * width + x])
             << ',' << int(costs[y * width + x]) << '\n';
      }
    }

    std::ofstream path(prefix + "_path.csv");
    path << "x,y\n";
    for (int i = 0; i < point_count; ++i) {
      const double x = planner.getPathX()[i];
      const double y = planner.getPathY()[i];
      path << x << ',' << y << '\n';
      const double previous_x = i ? planner.getPathX()[i - 1] : x;
      const double previous_y = i ? planner.getPathY()[i - 1] : y;
      const double segment_length = std::hypot(x - previous_x, y - previous_y);
      length += resolution * segment_length;

      // 独立检查每条路径线段，采样间隔不超过 0.01 米。
      // 只检查路径顶点可能漏掉两个顶点之间的碰撞。
      const int steps = std::max(1, int(std::ceil(segment_length * 10)));
      for (int j = 0; j <= steps; ++j) {
        const double sample_x = previous_x + (x - previous_x) * j / steps;
        const double sample_y = previous_y + (y - previous_y) * j / steps;
        for (auto [ox, oy] : obstacles) {
          min_clearance = std::min(
              min_clearance, std::hypot(sample_x - ox, sample_y - oy) * resolution);
        }
      }
    }

    if (found) {
      collision_free = min_clearance >= clearance_cells * resolution;
      const double end_error = std::hypot(
          planner.getPathX()[point_count - 1] - goal[0],
          planner.getPathY()[point_count - 1] - goal[1]);
      all_passed = all_passed && collision_free && end_error <= 2;
    }
    const bool expected_found = scenario < 2;
    all_passed = all_passed && found == expected_found;
    results << scenario << ',' << found << ',' << point_count << ',' << length
            << ',' << (found ? min_clearance : 0) << ',' << collision_free
            << ',' << expected_found << '\n';
    std::cout << "scenario=" << scenario << " found=" << found
              << " points=" << point_count << " length_m=" << length
              << " collision_free=" << collision_free << '\n';
  }
  return all_passed ? 0 : 1;
}
