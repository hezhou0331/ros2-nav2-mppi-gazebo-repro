#pragma once
// AIRY 原生 XYZIRT 入口：绝对秒减去帧首秒，再转为 RoamerX 内部的毫秒。
// 不生成 Livox tag，不借用 Livox 线束过滤。仅接收校验后的原始布局。
#include "common.h"
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace m1_airy {
inline void decode(const sensor_msgs::msg::PointCloud2& msg,
                   robot::slam::CloudPtr& output, double blind, int stride) {
    using F = sensor_msgs::msg::PointField;
    if (msg.is_bigendian || stride < 1 || !std::isfinite(blind) || blind < 0)
        throw std::invalid_argument("AIRY: invalid endian/filter configuration");
    const char* names[] = {"x", "y", "z", "intensity", "ring", "timestamp"};
    const uint8_t types[] = {F::FLOAT32,F::FLOAT32,F::FLOAT32,F::FLOAT32,F::UINT16,F::FLOAT64};
    const size_t sizes[] = {4,4,4,4,2,8};
    size_t offsets[6];
    for (size_t i=0;i<6;++i) {
        auto f=std::find_if(msg.fields.begin(),msg.fields.end(),[&](const auto& v){return v.name==names[i];});
        if (f==msg.fields.end() || f->datatype!=types[i] || f->count!=1 ||
            size_t(f->offset)+sizes[i]>msg.point_step)
            throw std::invalid_argument("AIRY: missing or mismatched XYZIRT field");
        offsets[i]=f->offset;
    }
    if (!msg.width || !msg.height || msg.row_step<size_t(msg.width)*msg.point_step ||
        msg.data.size()!=size_t(msg.height)*msg.row_step)
        throw std::invalid_argument("AIRY: invalid cloud dimensions");
    const double start=double(msg.header.stamp.sec)+double(msg.header.stamp.nanosec)*1e-9;
    robot::slam::PointCloudType cloud;
    cloud.reserve(size_t(msg.width)*msg.height);
    size_t valid=0;
    for(size_t row=0;row<msg.height;++row) for(size_t col=0;col<msg.width;++col) {
        const auto* p=msg.data.data()+row*msg.row_step+col*msg.point_step;
        float xyz[4];uint16_t ring;double ts;
        for(size_t i=0;i<4;++i) std::memcpy(&xyz[i],p+offsets[i],4);
        std::memcpy(&ring,p+offsets[4],2);std::memcpy(&ts,p+offsets[5],8);
        if(!std::isfinite(xyz[0])||!std::isfinite(xyz[1])||!std::isfinite(xyz[2]))continue;
        const double dt=ts-start;
        // 帧长实测约 0.1 秒，0.12 秒为协议检查上限；越界整帧拒绝，不能静默截断。
        if(!std::isfinite(ts)||dt < -1e-6||dt>0.12||ring>=96||!std::isfinite(xyz[3]))
            throw std::invalid_argument("AIRY: invalid ring or point time");
        if(double(xyz[0])*xyz[0]+double(xyz[1])*xyz[1]+double(xyz[2])*xyz[2]<=blind*blind)continue;
        if(valid++%stride)continue;
        robot::slam::PointType point{};
        point.x=xyz[0];point.y=xyz[1];point.z=xyz[2];point.intensity=xyz[3];
        point.curvature=float(std::max(0.0,dt)*1000.0);cloud.push_back(point);
    }
    if(cloud.size()<2)throw std::invalid_argument("AIRY: too few finite points");
    // syncData 在 IMU 去畸变排序之前取最后一点时间，因此必须在入队前排序。
    std::stable_sort(cloud.begin(),cloud.end(),[](const auto&a,const auto&b){return a.curvature<b.curvature;});
    *output=std::move(cloud);
}
}
