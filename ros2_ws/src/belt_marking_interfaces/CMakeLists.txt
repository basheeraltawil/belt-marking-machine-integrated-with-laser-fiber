cmake_minimum_required(VERSION 3.8)
project(belt_marking_interfaces)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

file(GLOB MSG_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} msg/*.msg)
file(GLOB SRV_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} srv/*.srv)
file(GLOB ACTION_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} action/*.action)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${MSG_FILES}
  ${SRV_FILES}
  ${ACTION_FILES}
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
