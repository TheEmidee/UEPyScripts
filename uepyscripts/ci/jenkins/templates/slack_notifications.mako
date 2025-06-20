<%def name="libraries()">
@Library('slack-notifier@master')
</%def>

<%def name="on_build_failure()">
sendMessageToSlack( "Failed", "danger" )
</%def>

<%def name="on_build_unstable()">
sendMessageToSlack( "Unstable", "warning" )
</%def>

<%def name="on_build_success()">
sendMessageToSlack( "Success", "good" )
</%def>

<%def name="on_exception_thrown()">
sendMessageToSlack( "Failure", "danger", "Reason : " + err.toString() )
</%def>

<%def name="additional_functions()">
def sendMessageToSlack( String message, String color, String suffix = "" ) {
    <%text>
    String full_message = message + " : ${env.JOB_NAME} - ${env.CHANGE_BRANCH} #${env.BUILD_NUMBER} (<${env.BUILD_URL}|Open>)"

    if ( !( suffix?.trim() ) ) {
        full_message += " " + suffix
    }
    </%text>

    slackSend channel: '${feature_config['channel']}', color: color, message: full_message
}
</%def>