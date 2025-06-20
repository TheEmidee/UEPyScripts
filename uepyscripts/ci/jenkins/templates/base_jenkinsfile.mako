## templates/base_jenkinsfile.mako
## Base Jenkinsfile template that combines all feature outputs

${libraries}
${imports}

try {
    ${pre_build_steps}

    if ( currentBuild.result == 'UNSTABLE' ) {
        ${on_build_unstable}
    } else if ( currentBuild.result == 'FAILURE' ) {
        ${on_build_failure}
    } else {
        ${on_build_success}
    }

    ${post_build_steps}
} catch ( Exception err ) {
    ${on_exception_thrown}
} finally {
    ${on_finally}
}

${additional_functions}