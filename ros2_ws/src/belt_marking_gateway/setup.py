from setuptools import find_packages, setup

package_name = 'belt_marking_gateway'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Basheer Al-Tawil',
    maintainer_email='basheeraltaweel@gmail.com',
    description='Optional MQTT publisher and OPC UA server for the belt marking machine.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mqtt_gateway = belt_marking_gateway.mqtt_node:main',
            'opcua_gateway = belt_marking_gateway.opcua_node:main',
        ],
    },
)
