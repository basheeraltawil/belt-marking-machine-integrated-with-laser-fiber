from setuptools import find_packages, setup

package_name = 'belt_marking_control'

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
    description='PackML state machine, job planner, alarms, recipes, production DB, OEE.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'control_node = belt_marking_control.control_node:main',
            'rviz_markers_node = belt_marking_control.rviz_markers_node:main',
            'run_scenarios = belt_marking_control.scenarios:main',
        ],
    },
)
