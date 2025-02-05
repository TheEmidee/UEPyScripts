from uepyscripts import logger
from uepyscripts import project
from uepyscripts.run import buildgraph

import json
from pathlib import Path

class BuildJob:
    name : str
    needs : list[str]

class BuildGroup:
    name : str
    jobs : list[BuildJob]

class BuildPlatform:
    name : str
    groups : list[BuildGroup]

class BuildContext:
    inlined_properties : str
    platforms : set[str]

    def __init__(
        self,
        json,
        buildgraph_properties : dict[str,str] = None ):

        if buildgraph_properties is not None:
            for key, value in buildgraph_properties.items():
                self.inlined_properties.append(f"-set:{key}={value}")

        for group in json['Groups']:
            name = group['Name']
            agent_types = group['Agent Types']
            nodes = group['Nodes']

            self.platforms.add(agent_types[0])

def read_json(path : Path ):
    with open(path) as f:
        return json.load(f)

def generate_jenkins_file(
    target: str, 
    properties : dict[str,str] = None 
    ):
    temp_folder = project.project_folders.saved_folders.temp
    export_path = temp_folder.joinpath("buildgraph.json")

    extra_parameters = fr"-Export\"{export_path}\" uebp_UATMutexNoWait=1 "

    buildgraph( target, properties, [ extra_parameters ] )
    json = read_json(export_path)
    build_context = BuildContext(json,properties)
    pass