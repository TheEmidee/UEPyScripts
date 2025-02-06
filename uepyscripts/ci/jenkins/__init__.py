from uepyscripts import logger
from uepyscripts import project
from uepyscripts.run import buildgraph
from uepyscripts.tools.algo.topological_order import Graph

import json
from pathlib import Path
from dataclasses import dataclass
from mako.template import Template

class BuildNode:
    def __init__(
        self,
        json_node
    ):
        self.name = json_node['Name']
        self.depends_on : list[str] = []
        
        depends_on = json_node['DependsOn']
        if depends_on:
            self.depends_on = depends_on.split(';')

class BuildGroup:
    def __init__(
        self,
        json_node
    ):
        self.name = json_node['Name']
        self.nodes = []
        for node in json_node['Nodes']:
            self.nodes.append(BuildNode(node))

class BuildPlatform:
    def __init__(
        self,
        name : str
    ):
        self.name = name
        self.job_to_group : dict[str,str] = {}
        self.groups : dict[str,BuildGroup] = {}
        self.parallel_groups : list[list[str]] = []

    def parse_group(self,json_node):
        group = BuildGroup(json_node)
        self.groups.update( { group.name : group } )

        for node in group.nodes:
            self.job_to_group.update( { node.name : group.name } )

    def build_parallel_groups(self):
        g = Graph()

        for group_name, group in self.groups.items():
            for node in group.nodes:
                for dependency in node.depends_on:
                    required_group_name = self.job_to_group[dependency]
                    if required_group_name != group.name:
                        g.add_edge(group.name,required_group_name)

        self.parallel_groups = g.topological_sort_with_hierarchy()

class BuildContext:
    def __init__(
        self,
        json,
        buildgraph_properties : dict[str,str] = None 
    ):
        self.inlined_properties : str = ""
        self.platforms : dict[str,BuildPlatform] = {}

        if buildgraph_properties is not None:
            for key, value in buildgraph_properties.items():
                self.inlined_properties += f"-set:{key}={value} "

        for group in json['Groups']:
            platform_name = group['Agent Types'][0]
            
            build_platform : BuildPlatform = None
            if platform_name not in self.platforms:
                build_platform = BuildPlatform(platform_name)
                self.platforms[platform_name] = build_platform
            else:
                build_platform = self.platforms[platform_name]

            build_platform.parse_group(group)

        for name, platform in self.platforms.items():
            platform.build_parallel_groups()

TEMPLATE = """
def properties = "${ctx.inlined_properties}"

% for platform_name,platform in ctx.platforms.items():
    % for group_names in platform.parallel_groups:
        jobs = [:]

        % for group_name in group_names:
            jobs[ "${group_name}" ] = {
                runBuildGraph( 
                    "${group_name}", 
                    [ 
                        % for node in platform.groups[group_name].nodes:
                            "${node.name}",
                        % endfor
                    ],
                    "${platform_name}",
                    properties 
                    )
            }
        % endfor

        jobs.failFast = true
        parallel jobs
    % endfor
% endfor
"""

def read_json(
    path : Path
):
    with open(path) as f:
        return json.load(f)

def generate_jenkins_file(
    target: str, 
    properties : dict[str,str] = None 
):
    temp_folder = project.project_folders.saved_folders.temp
    temp_folder.mkdir(exist_ok=True)

    export_path = temp_folder.joinpath("buildgraph.json")

    extra_parameters = [
        f"-Export={export_path}",
        "uebp_UATMutexNoWait=1"
    ]

    buildgraph( target, properties, extra_parameters )
    json = read_json(export_path)
    build_context = BuildContext(json,properties)

    tmp = Template(TEMPLATE)
    print(tmp.render(ctx=build_context))