// 真实 CDR 离线走与 mapping 相同的 AIRY 解码函数；无需启动建图或 ROS 发布。
#include "process/airy_preprocess.h"
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <fstream>
#include <iostream>
#include <iterator>
#include <iomanip>
int main(int argc,char**argv) {
    if(argc<2)return 2;
    for(int k=1;k<argc;++k) {
        std::ifstream file(argv[k],std::ios::binary);
        if(!file)throw std::runtime_error("CDR input unavailable");
        std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),{});
        rclcpp::SerializedMessage serialized(data.size());
        auto& raw=serialized.get_rcl_serialized_message();
        std::memcpy(raw.buffer,data.data(),data.size());raw.buffer_length=data.size();
        sensor_msgs::msg::PointCloud2 msg;
        rclcpp::Serialization<sensor_msgs::msg::PointCloud2> serializer;
        serializer.deserialize_message(&serialized,&msg);
        robot::slam::CloudPtr out(new robot::slam::PointCloudType);
        m1_airy::decode(msg,out,0.0,1);
        if(out->size()<1000 || out->back().curvature>120 || out->front().curvature<0)
            throw std::runtime_error("Unexpected native AIRY output");
        for(size_t i=1;i<out->size();++i)
            if(out->points[i].curvature<out->points[i-1].curvature)throw std::runtime_error("Unsorted point time");
        auto bad=msg;bad.fields.pop_back();bool rejected=false;
        try {m1_airy::decode(bad,out,0.0,1);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("Invalid schema accepted");
        bad=msg;bad.header.stamp.sec+=1;rejected=false;
        try {m1_airy::decode(bad,out,0.0,1);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("Invalid timestamp accepted");
        std::cout<<std::setprecision(9)<<"{\"input\":\""<<argv[k]<<"\",\"finite_points\":"<<out->size()
                 <<",\"first_ms\":"<<out->front().curvature<<",\"last_ms\":"<<out->back().curvature
                 <<",\"schema_rejection\":true,\"timestamp_rejection\":true}"<<std::endl;
    }
}
